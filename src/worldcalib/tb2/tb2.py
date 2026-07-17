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
    AutolabAttempt,
    AutolabHarborRunner,
    AutolabTask,
)
from worldcalib.schemas import TaskResult

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
    ) -> TaskResult:
        result = super()._build_task_result(
            task=task,
            attempts=attempts,
            job_dir=job_dir,
            returncode=returncode,
            timed_out=timed_out,
            duration_s=duration_s,
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
        test_output = render_test_output(trial_dir)
        if test_output:
            metadata["error_tail"] = test_output
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
