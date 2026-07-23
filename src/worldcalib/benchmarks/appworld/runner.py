"""External runner for AppWorld candidates (subprocess-harvest).

AppWorld eval cannot run in the worldcalib venv (pydantic-v1 vs v2). So each
candidate is evaluated by spawning :mod:`eval_entry` under the isolated
``.venv-appworld`` interpreter, passing the candidate's edited ``agent.py`` via
``--agent-path``. The subprocess runs the ReAct code agent over the split's tasks
(process-parallel), grades each with AppWorld's state-based unit tests, and writes
per-task raw dumps (``result.json`` + ``transcript.txt``). The runner then
harvests those into a :class:`CandidateResult`.

Mirrors the toolathlon ``ToolathlonSourceRunner`` contract; simpler because the
editable surface is a single file (``agent.py``) and there is no container farm.
"""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.paths import package_file, resolve_external_path, runtime_root
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult

from worldcalib.benchmarks.appworld.data import load_appworld_examples

DEFAULT_APPWORLD_AGENT_NAME = "appworld_passthrough"
DEFAULT_MAX_INTERACTIONS = 100  # AppWorld official ReAct budget (matches agent MAX_STEPS)
DEFAULT_CONCURRENCY = 64
DEFAULT_PER_TASK_TIMEOUT_S = 600

# Raw per-task evidence files the optimizer stages into the iter bundle so the
# proposer reads them directly (the agent's code transcript + the outcome).
_DUMP_EVIDENCE_FILES = ["result.json", "transcript.txt"]


class AppWorldSourceRunner:
    """Evaluate a source-backed AppWorld candidate (its ``agent.py``) on a split."""

    def __init__(
        self,
        *,
        examples: list[LocomoExample],
        out_dir: Path,
        model: str = "deepseek-v4-flash",
        concurrency: int = DEFAULT_CONCURRENCY,
        max_interactions: int = DEFAULT_MAX_INTERACTIONS,
        per_task_timeout_s: int = DEFAULT_PER_TASK_TIMEOUT_S,
        repeats: int = 1,
        appworld_root: Path | str | None = None,
        appworld_python: Path | str | None = None,
        dry_run: bool = False,
        force: bool = False,
        work_dir: Path | None = None,
    ) -> None:
        self.examples = examples
        self.out_dir = Path(out_dir)
        self.model = model
        self.concurrency = max(1, int(concurrency))
        self.max_interactions = int(max_interactions)
        self.per_task_timeout_s = int(per_task_timeout_s)
        # k-times averaging: each task is evaluated ``repeats`` times and the
        # per-task reward is the MEAN pass-rate (0, 1/k, …, 1). This shrinks the
        # single-eval Bernoulli variance by ~sqrt(k) so the optimizer ranks on the
        # task's pass *probability* rather than one coin flip (deepseek temp-0 MoE
        # nondeterminism flips ~20% of borderline AppWorld tasks per run).
        self.repeats = max(1, int(repeats))
        self.appworld_root = appworld_root
        self.appworld_python = appworld_python
        self.dry_run = dry_run
        self.force = force
        self.work_dir = runtime_root(work_dir)

    # ---- public API -------------------------------------------------------

    def evaluate_candidate(
        self,
        *,
        candidate: Mapping[str, Any],
        candidate_id: str,
        agent_name: str = DEFAULT_APPWORLD_AGENT_NAME,
    ) -> CandidateResult:
        candidate_dir = self.out_dir / "candidate_results"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        result_path = candidate_dir / f"{candidate_id}.json"
        if not self.force:
            existing = _load_candidate_result(
                result_path, candidate_id=candidate_id, agent_name=agent_name,
                config=dict(candidate),
            )
            if existing is not None:
                return existing

        if self.dry_run:
            task_results = [
                TaskResult(
                    task_id=ex.task_id, question=ex.sample_id, gold_answer="",
                    prediction="", score=0.0, passed=False,
                    prompt_tokens=0, completion_tokens=0, retrieved=[],
                    metadata={"benchmark": "appworld", "dry_run": True},
                )
                for ex in self.examples
            ]
        else:
            base_dump = self.out_dir / "agent_runs" / candidate_id / "dumps"
            agent_path = self._agent_path(candidate)
            if self.repeats <= 1:
                self._run_eval(
                    candidate_id=candidate_id, dump_path=base_dump, agent_path=agent_path,
                    experiment_name=_experiment_name(candidate_id, 0),
                )
                task_results = [self._harvest_task(ex, base_dump) for ex in self.examples]
            else:
                rep_dirs: list[Path] = []
                for j in range(self.repeats):
                    rep_dir = base_dump / f"rep{j}"
                    self._run_eval(
                        candidate_id=candidate_id, dump_path=rep_dir, agent_path=agent_path,
                        experiment_name=_experiment_name(candidate_id, j),
                        log_name=f"eval_rep{j}.log",
                    )
                    rep_dirs.append(rep_dir)
                task_results = [self._harvest_task_reps(ex, rep_dirs) for ex in self.examples]

        result = self._aggregate(
            task_results, candidate_id=candidate_id, agent_name=agent_name,
            candidate=candidate, result_path=result_path,
        )
        payload = {
            "candidate": result.to_dict(),
            "tasks": [item.to_dict() for item in task_results],
            "score_breakdown": _score_breakdown(task_results),
        }
        result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return result

    # ---- subprocess eval --------------------------------------------------

    def _agent_path(self, candidate: Mapping[str, Any]) -> Path:
        """Resolve the candidate's edited agent.py.

        A candidate that DECLARES a source path must resolve: silently falling
        back to the seed here evaluates the wrong artifact and poisons every
        downstream reading (score, traces, calibration grades) without any
        visible failure. Only a candidate with no declared source at all (the
        passthrough seed) may use the built-in seed agent.
        """
        source = _candidate_source_path(candidate)
        if source is not None:
            cand_agent = source / "agent.py"
            if cand_agent.exists():
                return cand_agent
            raise FileNotFoundError(
                f"candidate {candidate.get('candidate_id') or candidate.get('name')!r} "
                f"declared source path {source} but {cand_agent} does not exist; "
                "refusing to fall back to the seed agent"
            )
        return package_file("worldcalib.benchmarks.appworld", "agent.py")

    def _run_eval(
        self,
        *,
        candidate_id: str,
        dump_path: Path,
        agent_path: Path,
        experiment_name: str,
        log_name: str = "eval.log",
    ) -> None:
        dump_path.mkdir(parents=True, exist_ok=True)
        appworld_root = resolve_external_path(
            self.appworld_root,
            env_var="APPWORLD_ROOT",
            label="AppWorld data root",
        )
        python_raw = self.appworld_python or os.environ.get("APPWORLD_PYTHON") or sys.executable
        appworld_python = Path(python_raw).expanduser().resolve()
        if not appworld_python.is_file():
            raise FileNotFoundError(f"AppWorld Python interpreter not found: {appworld_python}")
        eval_entry = package_file("worldcalib.benchmarks.appworld", "eval_entry.py")
        ids = ",".join(ex.sample_id for ex in self.examples)

        command = [
            str(appworld_python), str(eval_entry),
            "--agent-path", str(agent_path),
            "--task-ids", ids,
            "--out", str(dump_path.resolve()),
            "--concurrency", str(self.concurrency),
            "--max-interactions", str(self.max_interactions),
            "--experiment-name", experiment_name,
        ]
        env = os.environ.copy()
        env["APPWORLD_ROOT"] = str(appworld_root)
        env["APPWORLD_MODEL"] = self.model

        waves = math.ceil(len(self.examples) / self.concurrency) if self.examples else 1
        wall = int(waves * self.per_task_timeout_s * 1.5) + 600
        log_path = self.out_dir / "agent_runs" / candidate_id / log_name
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                command, cwd=str(self.out_dir), stdout=log, stderr=subprocess.STDOUT,
                text=True, start_new_session=True, env=env,
            )
            try:
                proc.communicate(timeout=wall)
            except subprocess.TimeoutExpired:
                _terminate_process_group(proc)
                proc.communicate()

    # ---- harvesting -------------------------------------------------------

    def _harvest_task(self, ex: LocomoExample, dump_path: Path) -> TaskResult:
        raw_id = ex.sample_id
        task_dump = dump_path / raw_id
        res = _read_json(task_dump / "result.json")
        passed = bool(res.get("success")) if res else False
        prompt_tokens = int(res.get("prompt_tokens") or 0)
        completion_tokens = int(res.get("completion_tokens") or 0)
        metadata: dict[str, Any] = {
            "benchmark": "appworld",
            "question_type": "all",
            "appworld_task_id": raw_id,
            "steps": res.get("steps"),
            "pass_count": res.get("pass_count"),
            "total_count": res.get("total_count"),
            "run_status": ("ok" if res else "missing"),
            "task_dump": str(task_dump),
            "dump_evidence_files": list(_DUMP_EVIDENCE_FILES),
        }
        agent_error = res.get("agent_error") or res.get("error")
        if agent_error:
            metadata["error"] = str(agent_error)[-2000:]
        if not res:
            metadata["missing_result"] = True
        return TaskResult(
            task_id=ex.task_id,
            question=raw_id,
            gold_answer="",
            prediction=("success" if passed else "fail"),
            score=1.0 if passed else 0.0,
            passed=passed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            retrieved=[],
            metadata=metadata,
        )

    def _harvest_task_reps(self, ex: LocomoExample, rep_dirs: list[Path]) -> TaskResult:
        """Average a task's outcome over k repeat evals → fractional ``score``.

        ``score`` is the mean pass-rate (the low-variance reward the optimizer
        ranks on); ``passed`` is the majority vote (for binary breakdown counts).
        ``task_dump`` points at a FAILED rep when one exists (better evidence for
        the proposer than a lucky pass), else rep0. Tokens are the per-episode mean.
        """
        raw_id = ex.sample_id
        successes: list[bool] = []
        prompt_each: list[int] = []
        completion_each: list[int] = []
        steps_each: list[Any] = []
        first_error: str | None = None
        fail_dump: Path | None = None
        rep0_dump = rep_dirs[0] / raw_id if rep_dirs else None
        n_missing = 0
        for rd in rep_dirs:
            td = rd / raw_id
            res = _read_json(td / "result.json")
            if not res:
                n_missing += 1
                successes.append(False)
                if fail_dump is None:
                    fail_dump = td
                continue
            ok = bool(res.get("success"))
            successes.append(ok)
            prompt_each.append(int(res.get("prompt_tokens") or 0))
            completion_each.append(int(res.get("completion_tokens") or 0))
            steps_each.append(res.get("steps"))
            err = res.get("agent_error") or res.get("error")
            if err and first_error is None:
                first_error = str(err)[-2000:]
            if not ok and fail_dump is None:
                fail_dump = td
        n = len(successes)
        n_pass = sum(1 for s in successes if s)
        score = n_pass / n if n else 0.0
        passed = n_pass * 2 >= n  # majority vote (ties → pass)
        prompt_tokens = round(sum(prompt_each) / len(prompt_each)) if prompt_each else 0
        completion_tokens = round(sum(completion_each) / len(completion_each)) if completion_each else 0
        evidence_dump = fail_dump or rep0_dump
        metadata: dict[str, Any] = {
            "benchmark": "appworld",
            "question_type": "all",
            "appworld_task_id": raw_id,
            "reps": n,
            "rep_successes": successes,
            "mean_score": score,
            "steps_per_rep": steps_each,
            "run_status": ("ok" if n_missing < n else "missing"),
            "task_dump": str(evidence_dump) if evidence_dump else "",
            "dump_evidence_files": list(_DUMP_EVIDENCE_FILES),
            "total_prompt_tokens": sum(prompt_each),
            "total_completion_tokens": sum(completion_each),
        }
        if first_error:
            metadata["error"] = first_error
        if n_missing:
            metadata["missing_reps"] = n_missing
        return TaskResult(
            task_id=ex.task_id,
            question=raw_id,
            gold_answer="",
            prediction=f"{n_pass}/{n} pass",
            score=score,
            passed=passed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            retrieved=[],
            metadata=metadata,
        )

    def _aggregate(
        self,
        task_results: list[TaskResult],
        *,
        candidate_id: str,
        agent_name: str,
        candidate: Mapping[str, Any],
        result_path: Path,
    ) -> CandidateResult:
        count = len(task_results)
        # Reward = mean per-task fractional score (= expected pass probability).
        # For repeats=1 this equals the old binary passrate (score ∈ {0,1}); for
        # repeats>1 it is the low-variance averaged reward.
        passrate = sum(t.score for t in task_results) / count if count else 0.0
        average_score = passrate
        prompt_tokens = sum(t.prompt_tokens for t in task_results)
        completion_tokens = sum(t.completion_tokens for t in task_results)
        token_consuming = prompt_tokens + completion_tokens
        return CandidateResult(
            candidate_id=candidate_id,
            scaffold_name=agent_name,
            passrate=passrate,
            average_score=average_score,
            token_consuming=token_consuming,
            avg_token_consuming=(token_consuming / count if count else 0.0),
            avg_prompt_tokens=(prompt_tokens / count if count else 0.0),
            avg_completion_tokens=(completion_tokens / count if count else 0.0),
            count=count,
            config=dict(candidate),
            result_path=str(result_path),
        )


def run_appworld_frontier(
    *,
    out_dir: Path,
    split: str = "train",
    limit: int = 0,
    source_project_path: Path | None = None,
    model: str = "deepseek-v4-flash",
    concurrency: int = DEFAULT_CONCURRENCY,
    max_interactions: int = DEFAULT_MAX_INTERACTIONS,
    per_task_timeout_s: int = DEFAULT_PER_TASK_TIMEOUT_S,
    repeats: int = 1,
    dry_run: bool = False,
    force: bool = False,
    pareto_quality_threshold: float = 0.125,
    appworld_root: Path | str | None = None,
    appworld_python: Path | str | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Evaluate the seed AppWorld agent baseline = iter 0 frontier."""
    examples = load_appworld_examples(split, limit=limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate: dict[str, Any] = {
        "name": DEFAULT_APPWORLD_AGENT_NAME,
        "agent_name": DEFAULT_APPWORLD_AGENT_NAME,
    }
    if source_project_path:
        candidate["source_project_path"] = str(source_project_path)
    runner = AppWorldSourceRunner(
        examples=examples, out_dir=out_dir, model=model,
        concurrency=concurrency, max_interactions=max_interactions,
        per_task_timeout_s=per_task_timeout_s, repeats=repeats,
        dry_run=dry_run, force=force,
        appworld_root=appworld_root, appworld_python=appworld_python,
        work_dir=work_dir,
    )
    result = runner.evaluate_candidate(
        candidate=candidate,
        candidate_id=DEFAULT_APPWORLD_AGENT_NAME,
        agent_name=DEFAULT_APPWORLD_AGENT_NAME,
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
        "benchmark": "appworld",
        "target_system": DEFAULT_APPWORLD_AGENT_NAME,
        "split": split,
        "limit": limit,
        "count": len(examples),
        "dry_run": dry_run,
        "candidate_count": 1,
        "candidates": [result.to_dict()],
        "pareto_frontier_path": str(frontier_path),
    }
    (out_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


# ---- helpers --------------------------------------------------------------


def _experiment_name(candidate_id: str, rep: int) -> str:
    """Filesystem-safe, unique AppWorld experiment name per candidate × rep.

    Keeps concurrent candidates / arms / reps from sharing AppWorld output dirs
    (the eval engine otherwise derives the name from the dump dir basename, which
    collides across candidates).
    """
    safe = "".join(c if (c.isalnum() or c in "_-") else "_" for c in candidate_id)
    return f"awc_{safe}_r{rep}"


def _candidate_source_path(candidate: Mapping[str, Any]) -> Path | None:
    extra = candidate.get("extra") if isinstance(candidate.get("extra"), Mapping) else {}
    for key in ("source_project_path", "upstream_source_path", "appworld_source_path"):
        value = candidate.get(key) or extra.get(key)
        if value:
            return Path(str(value)).expanduser()
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _score_breakdown(task_results: list[TaskResult]) -> dict[str, dict[str, object]]:
    """All-bucket + per-task buckets (AppWorld has a single 'all' task-type)."""

    def agg(items: list[TaskResult]) -> dict[str, object]:
        n = len(items)
        return {
            "count": n,
            "passrate": (sum(1 for i in items if i.passed) / n) if n else 0.0,
            "average_score": (sum(i.score for i in items) / n) if n else 0.0,
        }

    breakdown: dict[str, dict[str, object]] = {"all": agg(task_results)}
    for item in task_results:
        breakdown[item.task_id] = {
            "count": 1,
            "passrate": 1.0 if item.passed else 0.0,
            "average_score": float(item.score),
        }
    return breakdown


def _terminate_process_group(proc: "subprocess.Popen[str]") -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
        proc.wait(timeout=5)
        return
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _load_candidate_result(
    result_path: Path,
    *,
    candidate_id: str,
    agent_name: str,
    config: dict[str, Any],
) -> CandidateResult | None:
    if not result_path.exists():
        return None
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        candidate = CandidateResult.from_dict(payload["candidate"])
    except Exception:
        return None
    if (
        candidate.candidate_id != candidate_id
        or candidate.scaffold_name != agent_name
        or candidate.config != config
    ):
        return None
    return candidate
