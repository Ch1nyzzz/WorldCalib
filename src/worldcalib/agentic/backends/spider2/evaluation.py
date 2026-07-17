"""Spider2 evaluation runner — score a ``Spider2Scaffold`` over local tasks.

Mirrors the GAIA runner: a ``ThreadPoolExecutor`` over ``(example, run_idx)``
jobs (generation is I/O-bound on the LLM, so threads give the concurrency), a
**fresh** scaffold per task, execution-based scoring via
:func:`worldcalib.agentic.backends.spider2.scorer.score_sql`, and the shared
:mod:`worldcalib.optcore.evaluation` helpers for the failure row and the
candidate summary.

The gold-free **task view** is built here (host-side): it carries the question,
the db name, the external knowledge, the DB schema (DDL), and an absolute
read-only ``db_path`` — so the editable scaffold needs no repo paths and the
proposer can still evolve schema representation or sample rows from ``db_path``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from worldcalib.agentic.backends.spider2.base import Spider2Scaffold
from worldcalib.agentic.backends.spider2.data import db_path_of, schema_of
from worldcalib.agentic.backends.spider2.scorer import score_sql
from worldcalib.optcore.evaluation import build_error_task_result, summarize_candidate
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult


def _task_view(example: LocomoExample) -> dict[str, Any]:
    md = example.metadata
    db = str(md.get("db") or "")
    return {
        "instance_id": md.get("instance_id") or example.sample_id,
        "db": db,
        "question": example.question,
        "external_knowledge": md.get("external_knowledge") or "",
        "schema": schema_of(db),
        "db_path": str(db_path_of(db)),
    }


class Spider2EvaluationRunner:
    """Evaluate a ``Spider2Scaffold`` over a Spider2-lite train/test split."""

    def __init__(
        self,
        *,
        examples: list[LocomoExample],
        out_dir: Path,
        runs: int = 1,
        concurrency: int = 8,
    ) -> None:
        self.examples = examples
        self.out_dir = Path(out_dir)
        self.runs = max(1, runs)
        self.concurrency = max(1, concurrency)

    # ── public API (matches the optimizer main loop) ─────────────────────────

    def evaluate_scaffold(
        self,
        *,
        scaffold: Spider2Scaffold,
        scaffold_name: str,
        config: ScaffoldConfig,
        candidate_id: str,
    ) -> CandidateResult:
        task_results = self._run_all(scaffold)
        return summarize_candidate(
            task_results=task_results,
            scaffold_name=scaffold_name,
            config=config,
            candidate_id=candidate_id,
            out_dir=self.out_dir,
        )

    # ── task execution ───────────────────────────────────────────────────────

    def _run_all(self, scaffold: Spider2Scaffold) -> list[TaskResult]:
        jobs = [
            (example, run_idx)
            for run_idx in range(self.runs)
            for example in self.examples
        ]
        results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._run_one, scaffold, example): example
                for example, _ in jobs
            }
            for future in as_completed(futures):
                example = futures[future]
                out, error = future.result()
                results.append(self._to_task_result(example, out, error))
        return results

    def _run_one(
        self, scaffold: Spider2Scaffold, example: LocomoExample
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Run one task. Returns (solve_output, error_str). Never raises."""
        try:
            out = scaffold.fresh().solve_task(_task_view(example))
            return out, out.get("error")
        except Exception as exc:  # noqa: BLE001 — one bad task must not kill the eval
            return None, f"{type(exc).__name__}: {exc}"

    def _to_task_result(
        self, example: LocomoExample, out: dict[str, Any] | None, error: str | None
    ) -> TaskResult:
        question_type = str(example.metadata.get("question_type") or "all")
        instance_id = str(example.metadata.get("instance_id") or example.sample_id)

        if out is None:
            return build_error_task_result(
                example,
                error=error or "unknown error",
                status="error",
                domain="spider2",
            )

        sql = str(out.get("sql") or "")
        grade = score_sql(instance_id, sql)
        score = 1.0 if grade.passed else 0.0

        return TaskResult(
            task_id=example.task_id,
            question=example.question,
            # The table the SQL was graded against. Paired with `result_preview`
            # below, this is the whole diagnosis: neither is legible alone.
            gold_answer=grade.gold_preview,
            prediction=sql,
            score=score,
            passed=grade.passed,
            prompt_tokens=int(out.get("prompt_tokens") or 0),
            completion_tokens=int(out.get("completion_tokens") or 0),
            retrieved=[],
            metadata={
                "question_type": question_type,
                "status": "error" if out.get("error") else "completed",
                "error": out.get("error"),
                "grade_error": grade.error,
                # What the candidate's OWN query returned. A "Result Error" says
                # only THAT the rows were wrong; this says HOW they were wrong.
                "result_preview": grade.result_preview,
                "db": example.metadata.get("db"),
                "instance_id": instance_id,
                "domain": "spider2",
            },
        )
