"""AutoLab adapter.

AutoLab cases produced by the harbor / terminus-2 runner carry their useful
information in ``metadata`` rather than in the QA-style question/gold/prediction
slots — scoring is via a continuous harbor reward in ``[0, 1]`` (0.5 anchored to
a human reference solution), not text comparison.

Mapping into the unified Trace summary:

  - question   = "<task_id> [<domain>]"  (the task instruction lives in the
                 raw task dict but is large; keep the summary compact)
  - gold       = "reward >= gate"          (semantic placeholder)
  - prediction = best-attempt trial name   (or "<no trial produced>")
  - passed     = task['passed']
  - score      = task['score']             (CONTINUOUS reward)
  - domain / metric / direction / avg_at_k / best_at_k / rewards / k and the
    harbor jobs_dir are kept in the summary so trace-level tools can surface
    them on demand.
"""

from __future__ import annotations

from typing import Any

from ..schema import Trace


def _summary(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    task_id = str(task.get("task_id") or "")
    domain = str(metadata.get("domain") or "")

    question = f"{task_id} [{domain}]" if domain else task_id

    prediction = str(task.get("prediction") or "")
    if not prediction:
        prediction = "<no trial produced>"

    return {
        "question": question,
        "gold": "reward >= gate",
        "prediction": prediction,
        "score": task.get("score"),
        "passed": bool(task.get("passed")),
        "domain": domain,
        "metric": metadata.get("metric"),
        "direction": metadata.get("direction"),
        "baseline_score": metadata.get("baseline_score"),
        "reference_score": metadata.get("reference_score"),
        "reward": metadata.get("reward"),
        "avg_at_k": metadata.get("avg_at_k"),
        "best_at_k": metadata.get("best_at_k"),
        "k": metadata.get("k"),
        "rewards": metadata.get("rewards"),
        "n_errored": metadata.get("n_errored"),
        "gpus": metadata.get("gpus"),
        "jobs_dir": metadata.get("jobs_dir"),
        "trial_dir": metadata.get("trial_dir"),
        "duration_s": metadata.get("duration_s"),
        "returncode": metadata.get("returncode"),
        "timed_out": metadata.get("timed_out"),
        "missing": metadata.get("missing"),
    }


class AutolabAdapter:
    name = "autolab"

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
