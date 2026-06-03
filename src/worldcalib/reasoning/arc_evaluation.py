"""ARC-AGI-2 evaluation runner — score an ``ArcScaffold`` over real tasks.

ARC-AGI-2 is a **single-shot reasoning** benchmark: each task is a json file
holding ``train`` demonstration grid-pairs plus one or more ``test`` entries, and
the solver must predict the output grid for every test input. Unlike the stateful
tau2 agent runner, there is no orchestrator, no user simulator and no environment
— solving a task is one (or a few, for pass@k) chat calls to the served target
model via :class:`~worldcalib.model.LocalModelClient`, exactly like the locomo
answer path. Scoring is exact grid match with pass@2: a test input counts as
solved if any of its first ``max_attempts`` candidate grids matches the withheld
gold output, and a task's score is the fraction of its test inputs solved
(continuous), so partial credit is preserved on multi-test tasks.

This runner mirrors :mod:`worldcalib.tau2_evaluation`: it exposes the same
``evaluate_scaffold(...)`` signature the optimizer main loop calls, builds a
``CandidateResult`` plus a ``candidate_results/<id>.json`` payload with a
**per-category score_breakdown** keyed by ``question_type`` (the task's output
grid-size-change axis) — the interface the self-distill prediction protocol reads.
Tasks run on a ``ThreadPoolExecutor`` (each ``solve_task`` issues blocking,
synchronous ``client.chat`` calls, so threads give the concurrency).

The test entries in an ARC task json **do** contain the gold ``output``; this
runner loads them aside and passes only the test *inputs* to the scaffold — the
gold outputs never reach ``solve_task``.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from worldcalib.model import LocalModelClient
from worldcalib.optcore.evaluation import build_error_task_result, summarize_candidate
from worldcalib.reasoning.arc_scaffolds.base import (
    ArcScaffold,
    ArcSolveResult,
    Grid,
    grids_equal,
)
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult

DEFAULT_ARC_MAX_TOKENS = 2048
DEFAULT_ARC_MAX_ATTEMPTS = 2


class ArcEvaluationRunner:
    """Evaluate an ``ArcScaffold`` over a split of ARC-AGI-2 tasks."""

    def __init__(
        self,
        *,
        examples: list[LocomoExample],
        out_dir: Path,
        model: str,
        base_url: str,
        api_key: str,
        timeout_s: int = 300,
        max_tokens: int = DEFAULT_ARC_MAX_TOKENS,
        max_attempts: int = DEFAULT_ARC_MAX_ATTEMPTS,
        runs: int = 1,
        concurrency: int = 8,
    ) -> None:
        self.examples = examples
        self.out_dir = Path(out_dir)
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.max_attempts = max(1, max_attempts)
        self.runs = max(1, runs)
        self.concurrency = max(1, concurrency)
        # One shared client across all tasks/threads (stateless chat-completions).
        self.client = LocalModelClient(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_s=self.timeout_s,
        )

    # ── public API (matches the optimizer main loop) ─────────────────────────

    def evaluate_scaffold(
        self,
        *,
        scaffold: ArcScaffold,
        scaffold_name: str,
        config: ScaffoldConfig,
        candidate_id: str,
    ) -> CandidateResult:
        task_results = self._run_all(scaffold, config)
        return self._summarize(task_results, scaffold_name, config, candidate_id)

    # ── task execution ───────────────────────────────────────────────────────

    def _run_all(
        self, scaffold: ArcScaffold, config: ScaffoldConfig
    ) -> list[TaskResult]:
        jobs = [
            (example, run_idx)
            for run_idx in range(self.runs)
            for example in self.examples
        ]
        results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._run_one, scaffold, config, example, run_idx): example
                for example, run_idx in jobs
            }
            for future in as_completed(futures):
                results.append(future.result())
        return results

    def _run_one(
        self,
        scaffold: ArcScaffold,
        config: ScaffoldConfig,
        example: LocomoExample,
        run_idx: int,
    ) -> TaskResult:
        """Score one task. Never raises — a bad task becomes a 0-score error row."""
        question_type = str(example.metadata.get("question_type") or "all")
        split = str(example.metadata.get("split") or "")

        try:
            task_path = example.metadata["task_path"]
            with Path(task_path).open("r", encoding="utf-8") as handle:
                task = json.load(handle)

            train: list[dict] = list(task.get("train", []))
            test_entries: list[dict] = list(task.get("test", []))
            test_inputs: list[Grid] = [entry["input"] for entry in test_entries]
            # Gold outputs are kept aside here and NEVER passed to the scaffold.
            gold_outputs: list[Grid] = [entry["output"] for entry in test_entries]
            num_test = len(test_inputs)

            result: ArcSolveResult = scaffold.fresh().solve_task(
                train=train,
                test_inputs=test_inputs,
                client=self.client,
                config=config,
                max_tokens=self.max_tokens,
                max_attempts=self.max_attempts,
            )

            solved_count = 0
            for idx in range(num_test):
                attempts = (
                    result.attempts[idx] if idx < len(result.attempts) else []
                )
                if any(
                    grids_equal(att, gold_outputs[idx])
                    for att in attempts[: self.max_attempts]
                ):
                    solved_count += 1

            score = solved_count / num_test if num_test else 0.0
            passed = score >= 1.0
            return TaskResult(
                task_id=example.task_id,
                question=example.task_id,
                gold_answer="",
                prediction=f"solved={solved_count}/{num_test}",
                score=score,
                passed=passed,
                prompt_tokens=int(result.prompt_tokens),
                completion_tokens=int(result.completion_tokens),
                retrieved=[],
                metadata={
                    "question_type": question_type,
                    "status": "completed",
                    "num_test": num_test,
                    "solved": solved_count,
                    "split": split,
                },
            )
        except Exception as exc:  # noqa: BLE001 — one bad task must not kill the eval
            return build_error_task_result(
                example,
                error=f"{type(exc).__name__}: {exc}",
                num_test=int(example.metadata.get("num_test") or 0),
                solved=0,
                split=split,
            )

    def _summarize(
        self,
        task_results: list[TaskResult],
        scaffold_name: str,
        config: ScaffoldConfig,
        candidate_id: str,
    ) -> CandidateResult:
        return summarize_candidate(
            task_results=task_results,
            scaffold_name=scaffold_name,
            config=config,
            candidate_id=candidate_id,
            out_dir=self.out_dir,
        )
