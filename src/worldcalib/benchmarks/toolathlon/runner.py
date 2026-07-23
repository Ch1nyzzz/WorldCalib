"""External containerized runner for Toolathlon candidates.

Unlike the in-process scaffolds (spider2/gaia), Toolathlon evaluates each task by
spawning a docker/podman container via the benchmark's own ``run_parallel.py``
scheduler. The container copies the agent source (``utils/``) and the task dir
(``docs/agent_system_prompt.md``) from the *host* working tree at run time, so a
candidate's edits take effect by overlaying them onto a per-run working tree.

Per candidate, ``evaluate_candidate`` :
  1. refreshes a per-run working tree (heavy dirs symlinked to canonical, the
     editable subset real-copied),
  2. overlays the candidate's edited source onto it (the 3 editable ``utils``
     modules + the shared ``agent_system_prompt.md`` propagated into every split
     task dir),
  3. runs ``run_parallel.py --task_list <split> --workers N`` once,
  4. harvests each task's ``eval_res.json`` (``pass``) + ``traj_log.json``
     (token stats) into a ``CandidateResult``.

The runner keeps each candidate isolated in its own working tree.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Mapping

from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.paths import resolve_external_path
from worldcalib.schemas import CandidateResult, TaskResult

from worldcalib.benchmarks.toolathlon.data import (
    TASKS_SUBDIR,
    ToolathlonTask,
    load_toolathlon_tasks,
)

DEFAULT_TOOLATHLON_AGENT_NAME = "toolathlon_passthrough"
DEFAULT_MAXSTEP = 50
DEFAULT_PER_TASK_TIMEOUT_S = 1800
DEFAULT_CONTAINER_RUNNER = "containerized"

# Canonical-relative paths of the editable agent-policy source. The candidate's
# The editable agent source is the WHOLE ``utils/`` tree (snapshot at
# upstream_source/toolathlon/utils); the candidate may edit any file there and
# add new files/modules. The agent prompt sits at AGENT_PROMPT_REL and is fanned
# out into every split task dir's docs/agent_system_prompt.md.
AGENT_PROMPT_REL = "agent_system_prompt.md"
_TASK_PROMPT_REL = "docs/agent_system_prompt.md"

# Top-level entries the working tree always real-copies (small + may be edited
# or sensitive to the PROJECT_ROOT=$(dirname scripts) resolution in
# run_single_containerized.sh). Everything else is symlinked to canonical.
_REAL_COPY_TOP = ("utils", "scripts", "main.py", "run_parallel.py")
# Never symlink/copy these (per-run/transient or huge build artifacts we recreate).
_SKIP_TOP = {"dumps_baseline", "results_smoke", "dumps_quick_start", "__pycache__"}


class ToolathlonSourceRunner:
    """Evaluate a source-backed Toolathlon candidate on the frozen split."""

    def __init__(
        self,
        *,
        tasks: list[ToolathlonTask],
        out_dir: Path,
        toolathlon_root: Path | str | None = None,
        model: str = "deepseek-v4-flash",
        provider: str = "unified",
        concurrency: int = 8,
        maxstep: int = DEFAULT_MAXSTEP,
        per_task_timeout_s: int = DEFAULT_PER_TASK_TIMEOUT_S,
        container_runner: str = DEFAULT_CONTAINER_RUNNER,
        dry_run: bool = False,
        force: bool = False,
    ) -> None:
        self.tasks = tasks
        self.out_dir = Path(out_dir)
        self.toolathlon_root = resolve_external_path(
            toolathlon_root,
            env_var="TOOLATHLON_ROOT",
            label="Toolathlon checkout",
        )
        self.model = model
        self.provider = provider
        self.concurrency = max(1, int(concurrency))
        self.maxstep = int(maxstep)
        self.per_task_timeout_s = int(per_task_timeout_s)
        self.container_runner = container_runner
        self.dry_run = dry_run
        self.force = force
        # One working tree per runner (i.e. per arm/run); reused across candidates.
        self.work_root = self.out_dir / "toolathlon_work"

    # ---- public API -------------------------------------------------------

    def evaluate_candidate(
        self,
        *,
        candidate: Mapping[str, Any],
        candidate_id: str,
        agent_name: str = DEFAULT_TOOLATHLON_AGENT_NAME,
    ) -> CandidateResult:
        candidate_dir = self.out_dir / "candidate_results"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        result_path = candidate_dir / f"{candidate_id}.json"
        if not self.force:
            existing = _load_candidate_result(
                result_path,
                candidate_id=candidate_id,
                agent_name=agent_name,
                config=dict(candidate),
            )
            if existing is not None:
                return existing

        if self.dry_run:
            task_results = [
                TaskResult(
                    task_id=t.task_id, question=t.app, gold_answer="",
                    prediction="", score=0.0, passed=False,
                    prompt_tokens=0, completion_tokens=0, retrieved=[],
                    metadata={"benchmark": "toolathlon", "dry_run": True, "app": t.app},
                )
                for t in self.tasks
            ]
        else:
            dump_path = self.out_dir / "agent_runs" / candidate_id / "dumps"
            self._prepare_work_tree(candidate)
            self._run_parallel(candidate_id=candidate_id, dump_path=dump_path)
            task_results = [self._harvest_task(t, dump_path) for t in self.tasks]

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

    # ---- working tree + overlay ------------------------------------------

    def _prepare_work_tree(self, candidate: Mapping[str, Any]) -> None:
        """Build (lazily) the symlink-farm working tree and overlay edits."""

        self._ensure_symlink_farm()
        self._overlay_split_task_dirs()
        source_path = _candidate_source_path(candidate)
        # Overlay the ENTIRE editable agent source (utils/) from the candidate
        # snapshot so the proposer can edit existing modules AND add new
        # files/modules under it; fall back to canonical for the seed. Replaced
        # wholesale each candidate so a file added by one candidate never leaks
        # into the next.
        utils_src = (source_path / "utils") if source_path else None
        if not (utils_src and utils_src.exists()):
            utils_src = self.toolathlon_root / "utils"
        utils_dst = self.work_root / "utils"
        if utils_dst.exists() or utils_dst.is_symlink():
            shutil.rmtree(utils_dst)
        shutil.copytree(
            utils_src, utils_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        # Fan the shared agent prompt out into every split task dir.
        prompt_src = (source_path / AGENT_PROMPT_REL) if source_path else None
        if prompt_src and prompt_src.exists():
            prompt_text = prompt_src.read_text(encoding="utf-8")
            for task in self.tasks:
                tgt = self.work_root / "tasks" / TASKS_SUBDIR / task.task_id / _TASK_PROMPT_REL
                if tgt.parent.exists():
                    tgt.write_text(prompt_text, encoding="utf-8")

    def _ensure_symlink_farm(self) -> None:
        if (self.work_root / "run_parallel.py").exists() and (self.work_root / "utils").is_dir():
            return  # already built
        self.work_root.mkdir(parents=True, exist_ok=True)
        for entry in sorted(os.listdir(self.toolathlon_root)):
            if entry in _SKIP_TOP or entry == "tasks":
                continue
            src = self.toolathlon_root / entry
            dst = self.work_root / entry
            if dst.exists() or dst.is_symlink():
                continue
            if entry in _REAL_COPY_TOP:
                if src.is_dir():
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    shutil.copy2(src, dst)
            else:
                dst.symlink_to(src)  # heavy/static -> canonical

    def _overlay_split_task_dirs(self) -> None:
        """Real-copy each split task dir so per-task prompt edits don't touch canonical."""

        dst_root = self.work_root / "tasks" / TASKS_SUBDIR
        dst_root.mkdir(parents=True, exist_ok=True)
        for task in self.tasks:
            dst = dst_root / task.task_id
            if dst.exists():
                continue
            src = self.toolathlon_root / "tasks" / TASKS_SUBDIR / task.task_id
            if src.exists():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # ---- run_parallel invocation -----------------------------------------

    def _run_parallel(self, *, candidate_id: str, dump_path: Path) -> None:
        dump_path.mkdir(parents=True, exist_ok=True)
        task_list_file = self.out_dir / "agent_runs" / candidate_id / "task_list.txt"
        task_list_file.parent.mkdir(parents=True, exist_ok=True)
        # run_parallel matches bare task names (task_dir_arg.split('/')[-1]),
        # so the task_list holds bare ids, not "finalpool/<id>".
        task_list_file.write_text(
            "\n".join(t.task_id for t in self.tasks) + "\n", encoding="utf-8"
        )
        command = [
            "uv", "run", "python", "run_parallel.py",
            "--tasks_folder", TASKS_SUBDIR,
            "--task_list", str(task_list_file.resolve()),
            "--tag", candidate_id[:40],
            "--model_short_name", self.model,
            "--provider", self.provider,
            "--maxstep", str(self.maxstep),
            "--workers", str(self.concurrency),
            "--timeout", str(self.per_task_timeout_s),
            "--dump_path", str(dump_path.resolve()),
            "--runner", self.container_runner,
        ]
        # Candidate-level wall timeout: waves of `concurrency` tasks, each up to
        # per_task_timeout, plus container churn slack.
        waves = math.ceil(len(self.tasks) / self.concurrency) if self.tasks else 1
        wall = int(waves * self.per_task_timeout_s * 1.5) + 900
        log_path = self.out_dir / "agent_runs" / candidate_id / "run_parallel.log"
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                command, cwd=self.work_root, stdout=log, stderr=subprocess.STDOUT,
                text=True, start_new_session=True, env=os.environ.copy(),
            )
            try:
                proc.communicate(timeout=wall)
            except subprocess.TimeoutExpired:
                _terminate_process_group(proc)
                proc.communicate()

    # ---- harvesting -------------------------------------------------------

    def _harvest_task(self, task: ToolathlonTask, dump_path: Path) -> TaskResult:
        task_dump = dump_path / TASKS_SUBDIR / task.task_id
        eval_res = _read_json(task_dump / "eval_res.json")
        traj = _read_json(task_dump / "traj_log.json")
        passed = bool(eval_res.get("pass")) if eval_res else False
        stats = (traj.get("key_stats") or {}) if traj else {}
        prompt_tokens = int(stats.get("input_tokens") or 0)
        completion_tokens = int(stats.get("output_tokens") or 0)
        # eval_detail relays the BENCHMARK's own verdict verbatim — that is raw
        # evidence, not our diagnosis. We do NOT fabricate a cause (no "crashed
        # before any LLM call" headline) and do NOT inline a traceback here. The
        # COMPLETE verdict + any runtime traceback are staged as raw files
        # (eval_res.json + run.log, declared in metadata['dump_evidence_files']
        # and copied into the iter bundle by the optimizer), which the proposer
        # reads and attributes itself. Harvest is a faithful translator, not a
        # diagnostician.
        detail = ""
        if eval_res:
            detail = str(eval_res.get("details") or eval_res.get("failure") or "")
        # A verbatim traceback TAIL (no headline) is kept in metadata for quick
        # triage when the episode actually crashed (a real runner error, or no
        # recorded tokens) — useful for spotting a broken candidate at a glance;
        # the full log is in the staged run.log.
        crash_error = ""
        if not passed:
            zero_tokens = prompt_tokens == 0 and completion_tokens == 0
            found = _extract_crash_error(task_dump)
            if found and (zero_tokens or "Error when running agent" in found):
                crash_error = found
        metadata: dict[str, Any] = {
            "benchmark": "toolathlon",
            "app": task.app,
            "servers": list(task.servers),
            "run_status": (traj.get("status") if traj else None),
            "total_turns": stats.get("total_turns"),
            "tool_calls": stats.get("tool_calls"),
            "eval_detail": detail[:1500],
            "task_dump": str(task_dump),
            # Raw diagnostic files the optimizer stages into the iter bundle so
            # the proposer reads them directly (see _stage_task_dump_evidence).
            "dump_evidence_files": ["eval_res.json", "run.log"],
        }
        if crash_error:
            metadata["error"] = crash_error[-2000:]
        if not eval_res:
            metadata["missing_eval_res"] = True
        return TaskResult(
            task_id=task.task_id,
            question=task.app,
            gold_answer="",
            prediction=(traj.get("status") if traj else "") or "",
            score=1.0 if passed else 0.0,
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
        passrate = sum(1 for t in task_results if t.passed) / count if count else 0.0
        average_score = sum(t.score for t in task_results) / count if count else 0.0
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


def run_toolathlon_frontier(
    *,
    out_dir: Path,
    split: str = "train",
    limit: int = 0,
    source_project_path: Path | None = None,
    model: str = "deepseek-v4-flash",
    provider: str = "unified",
    concurrency: int = 8,
    maxstep: int = DEFAULT_MAXSTEP,
    per_task_timeout_s: int = DEFAULT_PER_TASK_TIMEOUT_S,
    dry_run: bool = False,
    force: bool = False,
    pareto_quality_threshold: float = 0.125,
    toolathlon_root: Path | str | None = None,
) -> dict[str, Any]:
    """Evaluate the default (seed) Toolathlon agent baseline = iter 0 frontier."""

    tasks = load_toolathlon_tasks(split, limit=limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate: dict[str, Any] = {
        "name": DEFAULT_TOOLATHLON_AGENT_NAME,
        "agent_name": DEFAULT_TOOLATHLON_AGENT_NAME,
    }
    if source_project_path:
        candidate["source_project_path"] = str(source_project_path)
    runner = ToolathlonSourceRunner(
        tasks=tasks, out_dir=out_dir, toolathlon_root=toolathlon_root, model=model, provider=provider,
        concurrency=concurrency, maxstep=maxstep,
        per_task_timeout_s=per_task_timeout_s, dry_run=dry_run, force=force,
    )
    result = runner.evaluate_candidate(
        candidate=candidate,
        candidate_id=DEFAULT_TOOLATHLON_AGENT_NAME,
        agent_name=DEFAULT_TOOLATHLON_AGENT_NAME,
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
        "benchmark": "toolathlon",
        "target_system": DEFAULT_TOOLATHLON_AGENT_NAME,
        "split": split,
        "limit": limit,
        "count": len(tasks),
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


def _candidate_source_path(candidate: Mapping[str, Any]) -> Path | None:
    extra = candidate.get("extra") if isinstance(candidate.get("extra"), Mapping) else {}
    for key in ("source_project_path", "upstream_source_path", "toolathlon_source_path"):
        value = candidate.get(key) or extra.get(key)
        if value:
            return Path(str(value)).expanduser()
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _extract_crash_error(task_dump: Path) -> str:
    """Pull the runtime traceback out of a task's ``run.log``.

    When a candidate breaks agent construction (e.g. registers a bad local
    tool), the episode dies before any LLM call: ``eval_res.json`` is empty and
    ``traj_log.json`` carries no detail, so the proposer sees only
    ``run_status=failed`` with no cause. The real reason — the Python traceback
    — lives in ``run.log``, which is otherwise outside the proposer's evidence
    bundle. Surface it so the next iteration can fix the actual bug instead of
    guessing. Returns "" when there is no traceback (normal completed episodes).
    """
    log = task_dump / "run.log"
    if not log.exists():
        return ""
    try:
        raw = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = [_ANSI_RE.sub("", ln).rstrip() for ln in raw.splitlines()]

    parts: list[str] = []
    # 1) The agent runner's one-line summary, if present (last occurrence).
    for ln in reversed(lines):
        if "Error when running agent" in ln:
            parts.append(ln.strip())
            break
    # 2) The last full traceback block: the ``Traceback`` marker, the indented
    #    frames, and the first following non-indented line (the exception).
    tb_start = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("Traceback (most recent call last):"):
            tb_start = i
            break
    if tb_start is not None:
        block = [lines[tb_start]]
        for ln in lines[tb_start + 1 :]:
            block.append(ln)
            if ln and not ln[0].isspace():  # exception summary line ends the block
                break
        parts.append("\n".join(block))

    return ("\n\n".join(p for p in parts if p)).strip()[:1500]


def _score_breakdown(task_results: list[TaskResult]) -> dict[str, dict[str, object]]:
    """All-bucket + per-app buckets + per-task buckets.

    The per-app buckets are the natural Toolathlon task-type axis; the per-task
    buckets let the calib proposer's Upside/Downside prediction name task_ids.
    """

    def agg(items: list[TaskResult]) -> dict[str, object]:
        n = len(items)
        return {
            "count": n,
            "passrate": (sum(1 for i in items if i.passed) / n) if n else 0.0,
            "average_score": (sum(i.score for i in items) / n) if n else 0.0,
        }

    breakdown: dict[str, dict[str, object]] = {"all": agg(task_results)}
    by_app: dict[str, list[TaskResult]] = {}
    for item in task_results:
        by_app.setdefault(str(item.metadata.get("app") or "all"), []).append(item)
    for app, items in by_app.items():
        breakdown[f"app::{app}"] = agg(items)
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
