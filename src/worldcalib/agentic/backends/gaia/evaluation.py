"""GAIA evaluation runner — score a ``GaiaScaffold`` over GAIA episodes.

Mirrors the tau2 runner's shape: a ``ThreadPoolExecutor`` over
``(example, run_idx)`` jobs (the FC loop is synchronous and I/O-bound on LLM +
tool calls, so threads give the concurrency), a **fresh** scaffold per episode,
exact-match scoring via the vendored official ``question_scorer``, and the
shared :mod:`worldcalib.optcore.evaluation` helpers for the failure row and the
candidate summary. ``question_type`` is the GAIA ``level`` (``"level_1"`` …) —
the per-category axis the self-distill prediction protocol reads.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from worldcalib.agentic.backends.gaia.base import GaiaScaffold
from worldcalib.agentic.backends.gaia.scorer import question_scorer
from worldcalib.optcore.evaluation import build_error_task_result, summarize_candidate
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult


def _task_view(example: LocomoExample) -> dict[str, Any]:
    """A gold-free task view for the scaffold (the prompt is the example question)."""
    md = example.metadata
    return {
        "task_id": md.get("gaia_task_id") or example.sample_id,
        "level": md.get("level"),
        "file_name": md.get("file_name") or "",
        "prompt": example.question,
    }


class GaiaEvaluationRunner:
    """Evaluate a ``GaiaScaffold`` over a GAIA train/test split of episodes."""

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
        scaffold: GaiaScaffold,
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

    # ── episode execution ────────────────────────────────────────────────────

    def _run_all(self, scaffold: GaiaScaffold) -> list[TaskResult]:
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
        self, scaffold: GaiaScaffold, example: LocomoExample
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Run one episode. Returns (solve_output, error_str). Never raises."""
        try:
            out = scaffold.fresh().solve_task(_task_view(example))
            return out, out.get("error")
        except Exception as exc:  # noqa: BLE001 — one bad episode must not kill the eval
            return None, f"{type(exc).__name__}: {exc}"

    def _to_task_result(
        self, example: LocomoExample, out: dict[str, Any] | None, error: str | None
    ) -> TaskResult:
        question_type = str(example.metadata.get("question_type") or "all")

        if out is None:
            return build_error_task_result(
                example,
                error=error or "unknown error",
                status="error",
                domain="gaia",
            )

        answer = str(out.get("answer") or "")
        gold = example.answer
        passed = bool(question_scorer(answer, gold))
        score = 1.0 if passed else 0.0

        return TaskResult(
            task_id=example.task_id,
            question=example.question,
            gold_answer=gold,
            prediction=answer,
            score=score,
            passed=passed,
            prompt_tokens=int(out.get("prompt_tokens") or 0),
            completion_tokens=int(out.get("completion_tokens") or 0),
            retrieved=[],
            metadata={
                "question_type": question_type,
                "status": "error" if out.get("error") else "completed",
                "error": out.get("error"),
                "iterations": out.get("iterations"),
                "finish_reason": out.get("finish_reason"),
                "level": example.metadata.get("level"),
                "domain": "gaia",
            },
        )
