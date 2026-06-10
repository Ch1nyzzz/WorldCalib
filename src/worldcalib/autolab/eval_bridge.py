"""Host-side eval bridge for the AutoLab *designer* mode.

In designer mode the proposer runs as one long autonomous session inside its
docker sandbox and edits an editable terminus-2 source tree. The sandbox has no
``harbor`` install, so it cannot evaluate its own edits directly. Instead it
asks for an eval by dropping a request file into its workspace; this module is
the HOST-side counterpart that watches for those requests, runs the (heavy)
harbor evaluation on a TRAIN subset, and writes the aggregate result back.

The bridge is the only thing that runs harbor in designer mode, so it is also
where the guarantees live:

* **train/test separation** — it only ever loads ``split="train"`` tasks; the
  held-out ``test_split`` is run by the harness AFTER the session, never on an
  agent request.
* **anti reward-hacking** — it returns only aggregate score + per-task
  pass/fail + the agent-harness health flags (timed_out / errored). It never
  returns verifier internals or reward-file contents, and the agent is
  sandboxed away from the task containers regardless.
* **cost budget** — autolab tasks are expensive (a harbor subprocess each, some
  on GPU). Smoke and full evals each draw down a quota and the whole session
  has a wall-clock ceiling; once exhausted the bridge answers
  ``budget_exhausted`` instead of running.

Communication is a plain file protocol over the workspace bind mount
(``<cwd>`` on the host == ``/workspace`` in the container), so it needs no
networking. The in-sandbox client (``_designer_tools/eval.py`` /
``checkpoint.py``) writes workspace-RELATIVE paths; the bridge joins them onto
the host workspace root so a container ``/workspace/...`` path never leaks into
a host PYTHONPATH.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from worldcalib.autolab.autolab import (
    _TERMINUS2_PKG_MARKER,
    AutolabHarborRunner,
    AutolabTask,
)
from worldcalib.autolab.diff_classify import classify_change
from worldcalib.prediction_feedback import F2P, P2F, actual_flips, load_task_outcomes

# Workspace-relative directories of the file protocol (created by the bridge so
# the client can assume they exist).
EVAL_REQUEST_DIR = "eval_requests"
EVAL_RESULT_DIR = "eval_results"
CHECKPOINT_REQUEST_DIR = "checkpoint_requests"
CHECKPOINT_RESULT_DIR = "checkpoint_results"

# Default editable source root, relative to the designer workspace. The skill
# tells the agent its package lives here; the eval client defaults `--source`
# to it.
DEFAULT_SOURCE_REL = "terminus2_agent"


# A callable that builds a harbor runner for a given task subset + output dir +
# optional per-eval n_attempts (n=1 cheap probe, n>=2 confirm). Injected by the
# optimizer so all harbor config (binary / model / timeouts / env-file / workers)
# stays in one place and tests can pass a dry-run runner.
RunnerFactory = Callable[..., AutolabHarborRunner]
EventSink = Callable[[dict[str, Any]], None]


@dataclass
class DesignerBudget:
    """Hard ceilings for one designer session's self-service evals.

    The agent freely chooses which tasks to evaluate, so the cost cap is
    expressed in the units that actually cost: the cumulative number of harbor
    task-runs (``max_task_runs``) and the number of eval submissions
    (``max_eval_calls``), plus a session wall-clock ceiling. There is no fixed
    smoke/full quota — a 1-task probe and a 10-task full run both just draw down
    the same task-run pool by their size.
    """

    max_eval_calls: int = 40
    max_task_runs: int = 120
    max_wall_clock_s: float = 6 * 3600.0

    # mutable counters (mutated only by the bridge loop thread)
    calls_used: int = 0
    task_runs_used: int = 0
    started_at: float | None = None

    def wall_clock_used_s(self) -> float:
        return 0.0 if self.started_at is None else max(0.0, time.time() - self.started_at)

    def out_of_wall_clock(self) -> bool:
        return self.wall_clock_used_s() >= self.max_wall_clock_s

    def calls_remaining(self) -> int:
        return max(0, self.max_eval_calls - self.calls_used)

    def task_runs_remaining(self) -> int:
        return max(0, self.max_task_runs - self.task_runs_used)

    def exhausted(self) -> bool:
        """True when no further eval is possible at all (stop the session)."""
        return (
            self.out_of_wall_clock()
            or self.calls_remaining() <= 0
            or self.task_runs_remaining() <= 0
        )

    def can_run(self, n_tasks: int) -> bool:
        """Whether a request of `n_tasks` fits within what remains."""
        return (
            not self.out_of_wall_clock()
            and self.calls_remaining() > 0
            and self.task_runs_remaining() >= n_tasks
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "calls_used": self.calls_used,
            "calls_max": self.max_eval_calls,
            "task_runs_used": self.task_runs_used,
            "task_runs_max": self.max_task_runs,
            "task_runs_remaining": self.task_runs_remaining(),
            "wall_clock_used_s": round(self.wall_clock_used_s(), 1),
            "wall_clock_max_s": self.max_wall_clock_s,
            "exhausted": self.exhausted(),
        }


@dataclass
class CheckpointRecord:
    """A design the agent asked the harness to remember (frozen on the host)."""

    ckpt_id: str
    frozen_source_path: str
    note: str
    ts: str
    direction_tag: str = ""
    mechanism: str = ""
    diff_class: str = ""  # "code-level" | "prompt-level" | "none" (diff_classify hint)
    changed_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ckpt_id": self.ckpt_id,
            "frozen_source_path": self.frozen_source_path,
            "note": self.note,
            "ts": self.ts,
            "direction_tag": self.direction_tag,
            "mechanism": self.mechanism,
            "diff_class": self.diff_class,
            "changed_files": list(self.changed_files),
        }


class EvalBridge:
    """Watches a designer workspace for eval / checkpoint requests and serves
    them from the host, where harbor can actually run.

    Lifecycle: :meth:`start` spawns a daemon thread; :meth:`stop` joins it. The
    optimizer brackets the long ``_run_proposer_agent`` call with start/stop.
    """

    def __init__(
        self,
        *,
        workspace: Path,
        out_dir: Path,
        runner_factory: RunnerFactory,
        train_tasks: list[AutolabTask],
        base_outcomes: dict[str, bool],
        budget: DesignerBudget,
        baseline_source: Path | None = None,
        smoke_task_ids: tuple[str, ...] = (),
        smoke_size: int = 3,
        event_sink: EventSink | None = None,
        poll_interval_s: float = 2.0,
    ) -> None:
        self.workspace = Path(workspace)
        self.out_dir = Path(out_dir)
        self.runner_factory = runner_factory
        self.train_tasks = list(train_tasks)
        self.base_outcomes = dict(base_outcomes)
        self.budget = budget
        # Pristine baseline terminus-2 root; used to classify each checkpoint's
        # change as prompt-level vs code-level (a hint for the direction judge).
        self.baseline_source = Path(baseline_source) if baseline_source else None
        self.event_sink = event_sink
        self.poll_interval_s = max(0.2, float(poll_interval_s))

        self.smoke_tasks = self._resolve_smoke_tasks(smoke_task_ids, smoke_size)
        self.checkpoints: list[CheckpointRecord] = []
        # archive.json is the shared, persistent memory of explored directions —
        # the same artifact a later K-parallel fan-out would share across branches.
        self.archive_path = self.out_dir / "archive.json"

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_eval: set[str] = set()
        self._seen_checkpoint: set[str] = set()

        for rel in (
            EVAL_REQUEST_DIR,
            EVAL_RESULT_DIR,
            CHECKPOINT_REQUEST_DIR,
            CHECKPOINT_RESULT_DIR,
        ):
            (self.workspace / rel).mkdir(parents=True, exist_ok=True)
        (self.out_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
        (self.out_dir / "evals").mkdir(parents=True, exist_ok=True)

    # -- smoke subset -------------------------------------------------------

    def _resolve_smoke_tasks(
        self, smoke_task_ids: tuple[str, ...], smoke_size: int
    ) -> list[AutolabTask]:
        """Pick the cheap train subset for `--subset smoke`.

        Explicit ids win (intersected with the loaded train set). Otherwise
        default to the CPU-only train tasks (``gpus == 0``), fewest CPUs first,
        capped at ``smoke_size`` — the fastest things to iterate against.
        """

        by_id = {t.task_id: t for t in self.train_tasks}
        if smoke_task_ids:
            picked = [by_id[i] for i in smoke_task_ids if i in by_id]
            if picked:
                return picked
        cpu_only = sorted(
            (t for t in self.train_tasks if t.gpus == 0),
            key=lambda t: (t.cpus, t.task_id),
        )
        pool = cpu_only or sorted(self.train_tasks, key=lambda t: t.task_id)
        return pool[: max(1, smoke_size)]

    # -- thread lifecycle ---------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self.budget.started_at = time.time()
        self._thread = threading.Thread(
            target=self._loop, name="autolab-eval-bridge", daemon=True
        )
        self._thread.start()
        self._emit(
            {
                "event": "designer_bridge_started",
                "smoke_tasks": [t.task_id for t in self.smoke_tasks],
                "n_train_tasks": len(self.train_tasks),
                "budget": self.budget.snapshot(),
            }
        )

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._emit(
            {
                "event": "designer_bridge_stopped",
                "budget": self.budget.snapshot(),
                "n_checkpoints": len(self.checkpoints),
            }
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan_eval_requests()
                self._scan_checkpoint_requests()
            except Exception:  # noqa: BLE001 - a watcher crash must not kill the run
                self._emit(
                    {"event": "designer_bridge_error", "trace": traceback.format_exc()}
                )
            self._stop.wait(self.poll_interval_s)
        # one final drain so a request that landed during shutdown still answers
        try:
            self._scan_eval_requests()
            self._scan_checkpoint_requests()
        except Exception:  # noqa: BLE001
            pass

    # -- eval requests ------------------------------------------------------

    def _scan_eval_requests(self) -> None:
        req_dir = self.workspace / EVAL_REQUEST_DIR
        for req_path in sorted(req_dir.glob("*.json")):
            req_id = req_path.stem
            if req_id in self._seen_eval:
                continue
            self._seen_eval.add(req_id)
            try:
                request = json.loads(req_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self._write_eval_result(
                    req_id, {"status": "error", "error": f"unreadable request: {exc}"}
                )
                continue
            self._handle_eval_request(req_id, request)

    def _resolve_request_tasks(
        self, request: dict[str, Any]
    ) -> tuple[list[AutolabTask], list[str], str]:
        """Resolve which train tasks a request wants.

        Precedence: explicit ``task_ids`` (free choice) > ``subset`` shortcut
        (``train``/``full`` = all train; anything else = the smoke subset).
        Returns ``(tasks, unknown_ids, scope_label)``. ``unknown_ids`` are
        requested ids not in the train set (silently dropped, but reported).
        """

        by_id = {t.task_id: t for t in self.train_tasks}
        raw_ids = request.get("task_ids")
        if isinstance(raw_ids, str):
            raw_ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
        if raw_ids:
            picked = [by_id[i] for i in raw_ids if i in by_id]
            unknown = [i for i in raw_ids if i not in by_id]
            return picked, unknown, f"custom:{len(picked)}"
        subset = str(request.get("subset", "smoke")).lower()
        if subset in {"train", "full"}:
            return list(self.train_tasks), [], "train"
        return list(self.smoke_tasks), [], "smoke"

    def _handle_eval_request(self, req_id: str, request: dict[str, Any]) -> None:
        tasks, unknown, scope = self._resolve_request_tasks(request)

        # No valid tasks named — tell the agent what it CAN pick.
        if not tasks:
            self._write_eval_result(
                req_id,
                {
                    "status": "error",
                    "scope": scope,
                    "error": (
                        "no valid train tasks selected"
                        + (f" (unknown ids: {unknown})" if unknown else "")
                        + ". Available train tasks: "
                        + ", ".join(t.task_id for t in self.train_tasks)
                    ),
                    "available_tasks": [t.task_id for t in self.train_tasks],
                    "budget": self.budget.snapshot(),
                },
            )
            return

        # Budget gate. Distinguish "nothing left at all" (stop) from "this
        # request is too big, pick fewer" (retry smaller).
        n = len(tasks)
        if self.budget.exhausted():
            self._write_eval_result(
                req_id,
                {
                    "status": "budget_exhausted",
                    "scope": scope,
                    "message": (
                        "Eval budget exhausted. Make sure your best designs are "
                        "checkpointed (worldcalib-checkpoint), then wrap up."
                    ),
                    "budget": self.budget.snapshot(),
                },
            )
            self._emit({"event": "designer_eval_refused", "req_id": req_id, "scope": scope})
            return
        if not self.budget.can_run(n):
            self._write_eval_result(
                req_id,
                {
                    "status": "budget_insufficient",
                    "scope": scope,
                    "message": (
                        f"This request needs {n} task-runs but only "
                        f"{self.budget.task_runs_remaining()} remain. Eval fewer "
                        "tasks (use --tasks to pick a smaller set)."
                    ),
                    "budget": self.budget.snapshot(),
                },
            )
            self._emit({"event": "designer_eval_refused", "req_id": req_id, "scope": scope})
            return

        # Resolve the workspace-relative source path onto the host workspace.
        source_rel = str(request.get("source_rel") or DEFAULT_SOURCE_REL).lstrip("/")
        host_source = (self.workspace / source_rel).resolve()
        if not (host_source / _TERMINUS2_PKG_MARKER).is_file():
            self._write_eval_result(
                req_id,
                {
                    "status": "error",
                    "scope": scope,
                    "error": (
                        f"source {source_rel!r} is not a valid terminus-2 root "
                        f"(missing {_TERMINUS2_PKG_MARKER}); point --source at the "
                        "parent dir of the terminus_2 package."
                    ),
                    "budget": self.budget.snapshot(),
                },
            )
            return

        eval_out = self.out_dir / "evals" / req_id
        candidate = {
            "name": f"designer_{req_id}",
            "agent_source_path": str(host_source),
        }
        # n=1 is a cheap probe; n>=2 is a noise-reduced confirm. The agent picks
        # via `eval.py --attempts N`; default 1.
        n_attempts = max(1, int(request.get("n_attempts") or 1))
        started = time.time()
        try:
            runner = self.runner_factory(tasks, eval_out, n_attempts)
            result = runner.evaluate_candidate(
                candidate=candidate, candidate_id=f"designer_{req_id}"
            )
        except Exception as exc:  # noqa: BLE001 - report, do not crash the bridge
            self._write_eval_result(
                req_id,
                {
                    "status": "error",
                    "scope": scope,
                    "error": str(exc),
                    "budget": self.budget.snapshot(),
                },
            )
            self._emit(
                {
                    "event": "designer_eval_failed",
                    "req_id": req_id,
                    "scope": scope,
                    "error": str(exc),
                }
            )
            return

        # Draw down budget only on a real (non-error) eval.
        self.budget.calls_used += 1
        self.budget.task_runs_used += n

        payload = self._build_eval_payload(
            req_id, scope, result.result_path, duration_s=time.time() - started
        )
        payload["n_attempts"] = n_attempts
        if unknown:
            payload["unknown_task_ids"] = unknown
        self._write_eval_result(req_id, payload)
        self._emit(
            {
                "event": "designer_eval",
                "req_id": req_id,
                "scope": scope,
                "n_tasks": n,
                "passrate": payload.get("passrate"),
                "avg_score": payload.get("avg_score"),
                "net_flips": payload.get("net_flips"),
                "budget": payload.get("budget"),
            }
        )

    def _build_eval_payload(
        self, req_id: str, scope: str, result_path: str, *, duration_s: float
    ) -> dict[str, Any]:
        """Turn a candidate_results/*.json into the agent-facing summary.

        Returns only aggregate score + per-task pass/fail + flip vs the iter0
        baseline + agent-harness health flags. No verifier internals.
        """

        try:
            raw = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"status": "error", "scope": scope, "error": f"result read failed: {exc}"}

        cand_outcomes = load_task_outcomes(Path(result_path))
        flips = actual_flips(cand_outcomes, self.base_outcomes)

        per_task: list[dict[str, Any]] = []
        scores: list[float] = []
        n_pass = 0
        for t in raw.get("tasks") or []:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("task_id"))
            passed = bool(t.get("passed"))
            score = float(t.get("score") or 0.0)
            scores.append(score)
            n_pass += int(passed)
            meta = t.get("metadata") if isinstance(t.get("metadata"), dict) else {}
            per_task.append(
                {
                    "task_id": tid,
                    "score": round(score, 4),
                    "passed": passed,
                    "baseline_passed": self.base_outcomes.get(tid),
                    "flip": flips.get(tid, ""),
                    "timed_out": bool(meta.get("timed_out")),
                    "errored": bool(meta.get("n_errored")),
                    "jobs_dir": meta.get("jobs_dir"),
                }
            )
        per_task.sort(key=lambda r: r["task_id"])
        # Surface each task's agent trajectory (the agent's OWN harness log — NOT
        # verifier internals) into the workspace so the designer can read traces
        # and diagnose failure modes itself.
        traces_dir = self._surface_traces(req_id, per_task)
        for r in per_task:
            r.pop("jobs_dir", None)
        n = len(per_task)
        n_f2p = sum(1 for v in flips.values() if v == F2P)
        n_p2f = sum(1 for v in flips.values() if v == P2F)
        return {
            "status": "ok",
            "scope": scope,
            "req_id": req_id,
            "n_tasks": n,
            "passrate": round(n_pass / n, 4) if n else 0.0,
            "avg_score": round(sum(scores) / n, 4) if n else 0.0,
            "n_fail_to_pass": n_f2p,
            "n_pass_to_fail": n_p2f,
            "net_flips": n_f2p - n_p2f,
            "per_task": per_task,
            "duration_s": round(duration_s, 1),
            "result_path": str(result_path),
            "traces_dir": traces_dir,
            "budget": self.budget.snapshot(),
        }

    def _surface_traces(self, req_id: str, per_task: list[dict[str, Any]]) -> str | None:
        """Copy each task's agent trajectory (``job.log`` under its jobs_dir) into
        the workspace, bounded, so the sandboxed designer can read it. Returns the
        workspace-relative traces dir, or None if nothing was surfaced.

        This is the agent's OWN harness/solver log — it does not contain the
        verifier, reward files, or any task's reference solution.
        """
        rel = f"{EVAL_RESULT_DIR}/{req_id}__traces"
        dst = self.workspace / rel
        wrote = False
        for r in per_task:
            jobs_dir = r.get("jobs_dir")
            if not jobs_dir:
                continue
            log = Path(jobs_dir) / "job.log"
            if not log.is_file():
                continue
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Bound very large logs: keep head + tail so both the setup and the
            # finalize/failure are visible.
            cap = 80_000
            if len(text) > cap:
                head, tail = text[:25_000], text[-50_000:]
                text = f"{head}\n\n...[trace truncated, {len(text)} chars total]...\n\n{tail}"
            dst.mkdir(parents=True, exist_ok=True)
            (dst / f"{r['task_id']}.log").write_text(text, encoding="utf-8")
            wrote = True
        return rel if wrote else None

    def _write_eval_result(self, req_id: str, payload: dict[str, Any]) -> None:
        payload.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._atomic_write(self.workspace / EVAL_RESULT_DIR / f"{req_id}.json", payload)

    # -- checkpoint requests ------------------------------------------------

    def _scan_checkpoint_requests(self) -> None:
        req_dir = self.workspace / CHECKPOINT_REQUEST_DIR
        for req_path in sorted(req_dir.glob("*.json")):
            ckpt_id = req_path.stem
            if ckpt_id in self._seen_checkpoint:
                continue
            self._seen_checkpoint.add(ckpt_id)
            try:
                request = json.loads(req_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self._write_checkpoint_result(
                    ckpt_id, {"status": "error", "error": f"unreadable request: {exc}"}
                )
                continue
            self._handle_checkpoint_request(ckpt_id, request)

    def _handle_checkpoint_request(self, ckpt_id: str, request: dict[str, Any]) -> None:
        source_rel = str(request.get("source_rel") or DEFAULT_SOURCE_REL).lstrip("/")
        host_source = (self.workspace / source_rel).resolve()
        if not (host_source / _TERMINUS2_PKG_MARKER).is_file():
            self._write_checkpoint_result(
                ckpt_id,
                {
                    "status": "error",
                    "error": f"source {source_rel!r} is not a valid terminus-2 root",
                },
            )
            return

        # Freeze the current source so later edits in the same session cannot
        # mutate what this checkpoint refers to.
        frozen = self.out_dir / "checkpoints" / ckpt_id
        if frozen.exists():
            shutil.rmtree(frozen)
        frozen.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            host_source,
            frozen / "terminus2_agent",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        # Classify the change vs the pristine baseline (prompt-level vs code-level)
        # as a hint for the direction judge / the agent's own diversity tracking.
        diff_class, changed_files = "unknown", ()
        if self.baseline_source is not None:
            try:
                cls = classify_change(self.baseline_source, frozen / "terminus2_agent")
                diff_class = cls["class"]
                changed_files = tuple(cls["changed_files"])
            except Exception:  # noqa: BLE001 - classification is best-effort
                pass
        record = CheckpointRecord(
            ckpt_id=ckpt_id,
            frozen_source_path=str(frozen / "terminus2_agent"),
            note=str(request.get("note") or ""),
            ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
            direction_tag=str(request.get("direction") or ""),
            mechanism=str(request.get("mechanism") or ""),
            diff_class=diff_class,
            changed_files=changed_files,
        )
        self.checkpoints.append(record)
        self._write_archive()
        self._write_checkpoint_result(
            ckpt_id,
            {
                "status": "ok",
                "ckpt_id": ckpt_id,
                "frozen_source_path": record.frozen_source_path,
                "note": record.note,
                "direction": record.direction_tag,
                "diff_class": diff_class,
                "changed_files": list(changed_files),
                "n_checkpoints": len(self.checkpoints),
            },
        )
        self._emit(
            {
                "event": "designer_checkpoint",
                "ckpt_id": ckpt_id,
                "note": record.note,
                "direction": record.direction_tag,
                "diff_class": diff_class,
                "frozen_source_path": record.frozen_source_path,
            }
        )

    def _write_archive(self) -> None:
        """Persist the shared direction archive (the cross-round / cross-branch
        memory of what's been explored)."""
        self._atomic_write(
            self.archive_path,
            {"checkpoints": [c.to_dict() for c in self.checkpoints]},
        )

    def _write_checkpoint_result(self, ckpt_id: str, payload: dict[str, Any]) -> None:
        payload.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._atomic_write(
            self.workspace / CHECKPOINT_RESULT_DIR / f"{ckpt_id}.json", payload
        )

    # -- helpers ------------------------------------------------------------

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(dict(event))
        except Exception:  # noqa: BLE001 - logging must never break the bridge
            pass
