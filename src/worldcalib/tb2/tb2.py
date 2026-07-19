"""Terminal-Bench 2.0 runner — an editable terminus-2 driven through Harbor.

Terminal-Bench 2 and AutoLab are the same machine: Harbor runs an agent against a
task directory and a ``tests/`` verifier emits a reward. So this reuses
:class:`~worldcalib.autolab.autolab.AutolabHarborRunner` wholesale (argv building,
process-group timeouts, trial collection) and overrides exactly two seams:

- :meth:`Tb2HarborRunner._objective_value` — Terminal-Bench's published metric is
  pass@1 **averaged over repeats with MEAN** (tbench.ai / Artificial Analysis
  practice; never max). Rewards are binary (verified: 54 real trials, 32x ``0`` +
  22x ``1``), so with ``repeats=2`` a task scores 0, 0.5 or 1 — and thresholding
  that back into a bool would throw away precisely the noise reduction the second
  repeat was paid for.
- :meth:`Tb2HarborRunner._build_task_result` — the evidence. AutoLab's record
  keeps the reward and drops everything else (``prediction`` is the trial's
  *name*), which leaves a proposer asked to explain ``reward=0`` with nothing to
  read. Harbor already writes the whole story into each trial dir; this carries
  it onto the record.

Nothing here mutates AutoLab's behaviour: ``_objective_value``'s base
implementation is the fraction-of-passed AutoLab always computed.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from worldcalib.autolab.autolab import (
    DEFAULT_HARBOR_BINARY,
    DEFAULT_HARBOR_PYTHON,
    DEFAULT_REWARD_GATE,
    AutolabAttempt,
    AutolabHarborRunner,
    AutolabTask,
)
from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.schemas import TaskResult
from worldcalib.tb2.data import DEFAULT_TB2_DATASET, load_tb2_tasks

DEFAULT_TB2_AGENT = "terminus-2"
DEFAULT_TB2_SCAFFOLD_NAME = "terminus2_tb2"
# The frozen SUT, pinned to what putty's configs run as their frozen solver on
# the shared GPUGeek account. Deliberately NOT AutoLab's default: AutoLab runs
# deepseek-v4-pro[1m], and a stronger SUT would confound anything measured here
# with "a better model solves more".
#
# The ``openai/`` prefix is required and is not decoration. terminus-2 hands the
# name to LiteLLM, which infers the provider from it; ``Vendor3/DeepSeek-V4-Flash``
# is not a name LiteLLM knows, so without the prefix every trial dies at the first
# call with "LLM Provider NOT provided" (observed). AutoLab's default needs no
# prefix only because deepseek-v4-pro is a name LiteLLM already resolves. putty
# stores the bare name and prefixes it in code (terminalbench.py: f"openai/{model}");
# spider2 must NOT have the prefix, because it drives the OpenAI SDK directly
# rather than LiteLLM. Same model, three clients, three spellings.
DEFAULT_TB2_MODEL = "openai/Vendor3/DeepSeek-V4-Flash"
DEFAULT_TB2_API_BASE = "https://api.gpugeek.com/v1"
# terminus-2 reads this as an agent kwarg and hands it to LiteLLM; the matching
# key must reach the trial as OPENAI_API_KEY (the launcher exports it).
TB2_API_BASE_KWARG = "api_base"
# tb2 gets its own vendored copy so a candidate's edits here never reach the
# AutoLab experiments (both are gitignored under references/).
DEFAULT_TB2_TERMINUS2_SOURCE = Path("references/vendor/terminus2_agent_tb2")
# Terminal-Bench's published methodology: pass@1 x 2 repeats, MEAN-aggregated.
DEFAULT_TB2_REPEATS = 2
# Each concurrent trial takes its own Docker compose network and the host's
# default address pool holds ~31 in total, shared with everything else running.
# putty measured 16 exhausting the pool ("all predefined address pools have been
# fully subnetted") and failing 19 of 20 tasks. Leave real headroom.
DEFAULT_TB2_CONCURRENCY = 8

# A terminus rollout runs a few dozen turns; the sample trial inspected held 29
# steps / ~22KB, so most fit whole. Truncation keeps the TAIL: a terminal task is
# lost at the end, and the last commands are what explain the verdict.
_MAX_TRANSCRIPT_CHARS = 24000
_MAX_TEST_OUTPUT_CHARS = 4000
_MAX_PANE_CHARS = 2000


def render_transcript(trial_dir: Path) -> str:
    """The agent's rollout from Harbor's ATIF ``agent/trajectory.json``."""

    path = Path(trial_dir) / "agent" / "trajectory.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return ""
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        return ""
    lines: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        message = step.get("message")
        if not message:
            continue
        lines.append(f"[step {step.get('step_id')} {step.get('source')}] {message}")
    text = "\n".join(lines)
    if len(text) <= _MAX_TRANSCRIPT_CHARS:
        return text
    return "... (head truncated, tail kept) ...\n" + text[-_MAX_TRANSCRIPT_CHARS:]


def render_test_output(trial_dir: Path) -> str:
    """The verifier's own test log — which test failed, and how.

    ``reward=0`` says the tests failed; only this says which. pytest closes with
    its short summary (``FAILED <test> - <assertion>`` plus the counts), so the
    tail is the decisive part.
    """

    path = Path(trial_dir) / "verifier" / "test-stdout.txt"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.strip():
        return ""
    if len(text) <= _MAX_TEST_OUTPUT_CHARS:
        return text
    return "... (head truncated, tail kept) ...\n" + text[-_MAX_TEST_OUTPUT_CHARS:]


def read_test_summary(trial_dir: Path) -> dict[str, Any]:
    """Harbor's CTRF report summary — ``{tests, passed, failed, skipped, ...}``.

    Structured, so "12 failed, 1 passed" needs no log scraping.
    """

    path = Path(trial_dir) / "verifier" / "ctrf.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    results = payload.get("results")
    if not isinstance(results, dict):
        return {}
    summary = results.get("summary")
    return summary if isinstance(summary, dict) else {}


def render_crash(trial_dir: Path) -> str:
    """The trial's own traceback, when the agent died before the verifier ran.

    Harbor writes ``exception.txt`` and leaves ``verifier/`` empty, so a crashed
    trial has no test log by construction — its evidence lives here instead. Both
    failure classes must carry evidence or the only diagnosable failures become
    the ones that happen to take the branch that was wired.
    """

    path = Path(trial_dir) / "exception.txt"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.strip():
        return ""
    return text[-_MAX_TEST_OUTPUT_CHARS:]


def render_trial_log_tail(trial_dir: Path, *, max_chars: int = 2000) -> str:
    """Tail of Harbor's own trial log — the error message behind a traceback."""

    path = Path(trial_dir) / "trial.log"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:] if text.strip() else ""


def render_final_pane(trial_dir: Path) -> str:
    """The terminal as the agent left it — the state the verifier then judged."""

    path = Path(trial_dir) / "agent" / "terminus_2.pane"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.strip():
        return ""
    return text[-_MAX_PANE_CHARS:]


class Tb2HarborRunner(AutolabHarborRunner):
    """AutoLab's Harbor runner, scored by Terminal-Bench's metric and fully evidenced."""

    # Harbor writes all of these into each trial dir; the optimizer's dump stager
    # copies them into the proposer's bundle (see Optimizer._stage_task_dump_evidence).
    DUMP_EVIDENCE_FILES = (
        "verifier/test-stdout.txt",
        "verifier/ctrf.json",
        "agent/trajectory.json",
        "agent/terminus_2.pane",
        # Present only when the agent died before the verifier ran, which is
        # exactly when the verifier files are absent.
        "exception.txt",
        "trial.log",
    )

    def _objective_value(self, task_results: list[TaskResult]) -> float:
        """Mean of the per-task scores — Terminal-Bench's published metric."""

        count = len(task_results)
        return sum(t.score for t in task_results) / count if count else 0.0

    def _build_task_result(
        self,
        *,
        task: AutolabTask,
        attempts: list[AutolabAttempt],
        job_dir: Path,
        returncode: int | None,
        timed_out: bool,
        duration_s: float,
        infra_retries: int = 0,
    ) -> TaskResult:
        result = super()._build_task_result(
            task=task,
            attempts=attempts,
            job_dir=job_dir,
            returncode=returncode,
            timed_out=timed_out,
            duration_s=duration_s,
            infra_retries=infra_retries,
        )

        metadata = dict(result.metadata)
        # `solution/` is the task's reference solution. It rides the proposer's
        # record, never the agent's: a failed terminal rollout is unreadable
        # without knowing the intended approach, and telling "solved a different
        # problem" from "solved the right problem badly" is the diagnosis.
        gold = self._read_solution(task)

        trial_dir = self._best_trial_dir(attempts)
        if trial_dir is None:
            # No trial at all — the job broke before producing one. The base class
            # already attached harbor's stderr tail; there is no rollout to carry.
            metadata["task_dump"] = ""
            metadata["dump_evidence_files"] = []
            return dataclasses.replace(result, gold_answer=gold, metadata=metadata)

        metadata["task_dump"] = str(trial_dir)
        metadata["dump_evidence_files"] = list(self.DUMP_EVIDENCE_FILES)
        summary = read_test_summary(trial_dir)
        if summary:
            metadata["test_summary"] = summary
        # Two disjoint failure classes, both evidenced. The verifier's log exists
        # only when the verifier ran; a trial that crashed first has an
        # exception.txt and an empty verifier/ instead. Wiring one and not the
        # other is how a harness ends up able to explain only the failures it
        # happened to branch for.
        test_output = render_test_output(trial_dir)
        crash = render_crash(trial_dir)
        if test_output:
            metadata["error_tail"] = test_output
        elif crash:
            metadata["error_tail"] = crash
            metadata["crashed"] = True
            log_tail = render_trial_log_tail(trial_dir)
            if log_tail:
                metadata["trial_log_tail"] = log_tail
        pane = render_final_pane(trial_dir)
        if pane:
            metadata["final_pane"] = pane

        transcript = render_transcript(trial_dir)
        return dataclasses.replace(
            result,
            gold_answer=gold,
            # The rollout, not the trial's name.
            prediction=transcript or result.prediction,
            metadata=metadata,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _best_trial_dir(attempts: list[AutolabAttempt]) -> Path | None:
        """The trial dir the record's evidence is drawn from (the best attempt's)."""

        candidates = [a for a in attempts if a.trial_dir]
        if not candidates:
            return None
        best = max(candidates, key=lambda a: a.reward)
        path = Path(best.trial_dir)
        return path if path.is_dir() else None

    @staticmethod
    def _read_solution(task: AutolabTask, *, max_chars: int = 8000) -> str:
        sol_dir = Path(task.path) / "solution"
        if not sol_dir.is_dir():
            return ""
        parts: list[str] = []
        for path in sorted(sol_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parts.append(f"[{path.relative_to(sol_dir)}]\n{body.strip()}")
        text = "\n\n".join(parts)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n... (truncated)"


# ---------------------------------------------------------------------------
# Frontier (seed-baseline eval).
# ---------------------------------------------------------------------------
def run_tb2_frontier(
    *,
    out_dir: Path,
    tasks_path: Path | None = None,
    split: str = "train",
    limit: int = 0,
    task_ids: tuple[str, ...] = (),
    harbor_binary: Path = DEFAULT_HARBOR_BINARY,
    harbor_python: Path = DEFAULT_HARBOR_PYTHON,
    harbor_agent: str = DEFAULT_TB2_AGENT,
    harbor_model: str = DEFAULT_TB2_MODEL,
    api_base: str = DEFAULT_TB2_API_BASE,
    n_attempts: int = DEFAULT_TB2_REPEATS,
    timeout_multiplier: float = 1.0,
    concurrency: int = DEFAULT_TB2_CONCURRENCY,
    max_turns: int = 0,
    max_task_seconds: int = 0,
    env_file: Path | None = None,
    harbor_environment: str | None = None,
    reward_gate: float = DEFAULT_REWARD_GATE,
    # MEAN over repeats — Terminal-Bench's methodology. Must match what the
    # optimizer's iteration evals use (Tb2OptimizerConfig.score_mode), or the
    # seed baseline is aggregated differently from every candidate compared
    # against it. The runner's own default is "best", which silently inflated
    # split tasks (rewards [0,1] -> 1.0) until this was threaded through.
    score_mode: str = "avg",
    eval_timeout_s: int = 300,
    max_eval_workers: int = 1,
    dry_run: bool = False,
    force: bool = False,
    verify_patches: bool = True,
    pareto_quality_threshold: float = 0.125,
) -> dict[str, Any]:
    """Evaluate the pristine terminus-2 baseline (no agent-kwarg edits).

    Writes ``run_summary.json``, which is what a later run's ``SEED_FROM`` reads
    to share this iter-0 byte-identically across both arms.
    """

    tasks = load_tb2_tasks(
        tasks_path or DEFAULT_TB2_DATASET,
        split=split,
        limit=limit,
        task_ids=task_ids or (),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate: dict[str, Any] = {
        "name": DEFAULT_TB2_SCAFFOLD_NAME,
        "scaffold_name": DEFAULT_TB2_SCAFFOLD_NAME,
        "agent_name": DEFAULT_TB2_SCAFFOLD_NAME,
        "model": harbor_model,
        "agent_kwargs": {TB2_API_BASE_KWARG: api_base},
        "agent_env": {},
    }
    runner = Tb2HarborRunner(
        tasks=tasks,
        out_dir=out_dir,
        harbor_binary=harbor_binary,
        harbor_python=harbor_python,
        harbor_agent=harbor_agent,
        harbor_model=harbor_model,
        n_attempts=n_attempts,
        timeout_multiplier=timeout_multiplier,
        concurrency=concurrency,
        max_turns=max_turns,
        max_task_seconds=max_task_seconds,
        env_file=env_file,
        harbor_environment=harbor_environment,
        reward_gate=reward_gate,
        score_mode=score_mode,
        eval_timeout_s=eval_timeout_s,
        max_eval_workers=max_eval_workers,
        dry_run=dry_run,
        force=force,
        verify_patches=verify_patches,
    )
    result = runner.evaluate_candidate(
        candidate=candidate,
        candidate_id=DEFAULT_TB2_SCAFFOLD_NAME,
        agent_name=DEFAULT_TB2_SCAFFOLD_NAME,
    )
    frontier_path = out_dir / "pareto_frontier.json"
    save_frontier(
        frontier_path,
        [
            ParetoPoint(
                candidate_id=result.candidate_id,
                scaffold_name=result.scaffold_name,
                passrate=result.passrate,
                token_consuming=result.token_consuming,
                avg_token_consuming=result.avg_token_consuming,
                average_score=result.average_score,
                result_path=result.result_path,
                config=result.config,
            )
        ],
        quality_gap_threshold=pareto_quality_threshold,
    )
    summary = {
        "benchmark": "tb2",
        "target_system": DEFAULT_TB2_SCAFFOLD_NAME,
        "split": split,
        "limit": limit,
        "count": len(tasks),
        "dry_run": dry_run,
        "force": force,
        "candidate_count": 1,
        "candidates": [result.to_dict()],
        "pareto_frontier_path": str(frontier_path),
    }
    (out_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary
