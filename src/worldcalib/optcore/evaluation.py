"""Shared self-distill evaluation helpers.

The two backend evaluation runners (agentbench async ``SampleWorkflow`` vs tau2
``ThreadPoolExecutor`` + ``run_simulation``) build episodes differently, but the
**failed-episode row** and the **candidate summary** are identical in shape.
Those two pieces live here so both runners delegate to one implementation:

- :func:`build_error_task_result` — the score-0 ``TaskResult`` a runner emits
  when a single episode raises (isolated so one bad episode never crashes the
  batch).
- :func:`summarize_candidate` — aggregate ``TaskResult`` rows into a
  :class:`CandidateResult`, write ``candidate_results/<id>.json`` (with a
  per-category ``score_breakdown``), and return the candidate.

Token totals are computed uniformly from ``TaskResult.prompt_tokens`` /
``completion_tokens``: agentbench rows carry 0 tokens and therefore sum to 0
with no special-casing, while tau2 rows carry real counts.

Kept ``agentrl`` / ``tau2`` free.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcalib.evaluation import _score_breakdown
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult


def build_error_task_result(
    example: LocomoExample,
    *,
    error: str,
    status: str = "error",
    **extra_metadata: Any,
) -> TaskResult:
    """Build the score-0 ``TaskResult`` for an episode that failed to run.

    ``question_type`` is pulled from the example metadata (falling back to
    ``"all"``); ``status`` and ``error`` plus any ``extra_metadata`` (e.g. the
    episode ``index`` or ``domain``) are recorded on the row's metadata.
    """

    metadata: dict[str, Any] = {
        "question_type": str(example.metadata.get("question_type") or "all"),
        "status": status,
        "error": error,
    }
    metadata.update(extra_metadata)
    return TaskResult(
        task_id=example.task_id,
        question=example.task_id,
        gold_answer="",
        prediction="error",
        score=0.0,
        passed=False,
        prompt_tokens=0,
        completion_tokens=0,
        retrieved=[],
        metadata=metadata,
    )


def summarize_candidate(
    *,
    task_results: list[TaskResult],
    scaffold_name: str,
    config: ScaffoldConfig,
    candidate_id: str,
    out_dir: Path,
) -> CandidateResult:
    """Aggregate task results, write the candidate JSON, and return the candidate.

    Computes passrate / average_score and token totals uniformly from the task
    rows, writes ``<out_dir>/candidate_results/<candidate_id>.json`` containing
    ``{candidate, tasks, score_breakdown}``, and returns the
    :class:`CandidateResult`.
    """

    count = len(task_results)
    passrate = sum(1 for t in task_results if t.passed) / count if count else 0.0
    average_score = sum(t.score for t in task_results) / count if count else 0.0
    total_tokens = sum(t.prompt_tokens + t.completion_tokens for t in task_results)
    avg_tokens = total_tokens / count if count else 0.0
    avg_prompt = sum(t.prompt_tokens for t in task_results) / count if count else 0.0
    avg_completion = (
        sum(t.completion_tokens for t in task_results) / count if count else 0.0
    )

    candidate_dir = Path(out_dir) / "candidate_results"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    result_path = candidate_dir / f"{candidate_id}.json"

    candidate = CandidateResult(
        candidate_id=candidate_id,
        scaffold_name=scaffold_name,
        passrate=passrate,
        average_score=average_score,
        token_consuming=total_tokens,
        avg_token_consuming=avg_tokens,
        avg_prompt_tokens=avg_prompt,
        avg_completion_tokens=avg_completion,
        count=count,
        config=config.to_dict(),
        result_path=str(result_path),
    )
    payload = {
        "candidate": candidate.to_dict(),
        "tasks": [t.to_dict() for t in task_results],
        "score_breakdown": _score_breakdown(task_results),
    }
    result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return candidate
