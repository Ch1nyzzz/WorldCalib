"""Terminal-Bench 2.0 adapter.

TB2 records use the shared HarborRunner shape but
carry richer slots: ``prediction`` holds the agent's rendered rollout transcript
(tail-kept, up to ~24KB) and ``gold_answer`` holds the task's reference
solution. Both are too large for the compact Trace summary, so the summary
keeps size markers plus the per-trial evidence the runner distilled:

  - question     = "<task_id> [<domain>]"
  - gold         = "<solution: N chars>"    (or the placeholder when absent)
  - prediction   = "<transcript: N chars>"  (or "<no trial produced>")
  - passed/score = pass@1 x repeats, MEAN-aggregated (the published metric)
  - test_summary / error_tail / crashed / final_pane are the verifier-vs-crash
    evidence pair; trial_dir / task_dump locate the raw Harbor trial.
"""

from __future__ import annotations

from typing import Any

from ..schema import Trace


def _size_marker(text: Any, kind: str, empty: str) -> str:
    text = str(text or "")
    return f"<{kind}: {len(text)} chars>" if text.strip() else empty


def _summary(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    task_id = str(task.get("task_id") or "")
    domain = str(metadata.get("domain") or "")

    return {
        "question": f"{task_id} [{domain}]" if domain else task_id,
        "gold": _size_marker(task.get("gold_answer"), "solution", "<no reference solution>"),
        "prediction": _size_marker(task.get("prediction"), "transcript", "<no trial produced>"),
        "score": task.get("score"),
        "passed": bool(task.get("passed")),
        "domain": domain,
        "metric": metadata.get("metric"),
        "direction": metadata.get("direction"),
        "avg_at_k": metadata.get("avg_at_k"),
        "best_at_k": metadata.get("best_at_k"),
        "k": metadata.get("k"),
        "rewards": metadata.get("rewards"),
        "n_errored": metadata.get("n_errored"),
        "errors": metadata.get("errors"),
        "test_summary": metadata.get("test_summary"),
        "error_tail": metadata.get("error_tail"),
        "crashed": metadata.get("crashed"),
        "final_pane": metadata.get("final_pane"),
        "jobs_dir": metadata.get("jobs_dir"),
        "trial_dir": metadata.get("trial_dir"),
        "task_dump": metadata.get("task_dump"),
        "duration_s": metadata.get("duration_s"),
        "returncode": metadata.get("returncode"),
        "timed_out": metadata.get("timed_out"),
        "missing": metadata.get("missing"),
    }


class Tb2Adapter:
    name = "tb2"

    def build_trace(
        self,
        *,
        iteration: int,
        candidate_id: str,
        task: dict[str, Any],
    ) -> Trace:
        task_id = str(task.get("task_id") or "")
        return Trace(
            trace_id=f"iter{iteration:03d}_{candidate_id}_{task_id}",
            iteration=iteration,
            candidate_id=candidate_id,
            task_id=task_id,
            benchmark=self.name,
            summary=_summary(task),
            diff=None,
            spans=[],
        )
