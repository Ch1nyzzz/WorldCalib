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

# Grading-side renderers (deliberately NOT in arc_scaffolds/, which a candidate may
# edit). A 30x30 grid (ARC's max) renders to ~930 chars and a task holds up to ~15
# grids, so the cap must clear ~14KB: a truncated puzzle is a puzzle the proposer
# cannot solve, which is the failure this whole module exists to stop.
_MAX_RENDER_CHARS = 20000


def render_grid(grid: Grid | None) -> str:
    """One grid as ``<rows>x<cols>`` plus a digit-per-cell block."""

    if not grid:
        return "(none)"
    rows = ["".join(str(cell) for cell in row) for row in grid]
    return f"{len(grid)}x{len(grid[0]) if grid[0] else 0}\n" + "\n".join(rows)


def render_grids(grids: list[Grid]) -> str:
    """Several grids, indexed by test input."""

    if not grids:
        return "(none)"
    parts = [f"[test {i}]\n{render_grid(g)}" for i, g in enumerate(grids)]
    return _cap("\n".join(parts))


def render_attempts(attempts: list[list[Grid]]) -> str:
    """The candidate's ordered candidate grids per test input."""

    if not attempts:
        return "(no attempts — parsing produced nothing)"
    parts: list[str] = []
    for i, per_test in enumerate(attempts):
        if not per_test:
            parts.append(f"[test {i}] (no parsable grid)")
            continue
        for j, grid in enumerate(per_test):
            parts.append(f"[test {i} attempt {j}]\n{render_grid(grid)}")
    return _cap("\n".join(parts))


def render_arc_task(train: list[dict], test_inputs: list[Grid]) -> str:
    """The puzzle: the train input->output pairs plus the test input(s)."""

    parts: list[str] = []
    for i, pair in enumerate(train):
        parts.append(f"[train {i} input]\n{render_grid(pair.get('input'))}")
        parts.append(f"[train {i} output]\n{render_grid(pair.get('output'))}")
    for i, grid in enumerate(test_inputs):
        parts.append(f"[test {i} input]\n{render_grid(grid)}")
    return _cap("\n".join(parts))


def _cap(text: str) -> str:
    if len(text) <= _MAX_RENDER_CHARS:
        return text
    return text[:_MAX_RENDER_CHARS] + "\n... (truncated)"


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
                # The puzzle IS the question: without the train pairs and the test
                # input, a diagnosis of "solved=0/1" has nothing to reason about.
                question=render_arc_task(train, test_inputs),
                # Gold stays out of the SCAFFOLD (see above) but belongs in the
                # record the PROPOSER reads: comparing the predicted grid against
                # the intended one is what separates "misread the rule" from
                # "right rule, botched the render".
                gold_answer=render_grids(gold_outputs),
                # The candidate's actual output, not a tally of it.
                prediction=render_attempts(result.attempts),
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
