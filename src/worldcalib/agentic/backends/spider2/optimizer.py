"""Spider2 text-to-SQL agent-policy optimization.

Reuses the WorldCalib self-distill proposer loop to evolve a
``Spider2Scaffold`` (the single-shot text-to-SQL policy) — same protocol as the
other agentic backends: the proposer reads ``world_model_calibration.md``,
self-grades its previous prediction against the real outcome, and appends a
distill section — **no external critic**.

Evaluation runs real Spider2-lite local tasks via :class:`Spider2EvaluationRunner`
(generation over the locked DeepSeek SUT, execution-based scoring against the
bundled sqlite DBs), emitting a per-category ``score_breakdown`` keyed by
``question_type`` (a single ``"all"`` bucket today). The per-task ``tasks[]`` rows
carry each ``instance_id`` for the proposer's per-failure-mode reasoning.

The shared seed-frontier driver, WMC seeding, no-op critic, and example loader
live in :class:`SelfDistillOptimizer`; this module supplies only the
Spider2-specific hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.agentic.backends.spider2 import (
    DEFAULT_SPIDER2_SEED_SCAFFOLDS,
    build_spider2_scaffold,
)
from worldcalib.agentic.backends.spider2.data import load_spider2_examples
from worldcalib.agentic.backends.spider2.evaluation import Spider2EvaluationRunner
from worldcalib.benchmark_workspaces import (
    SPIDER2_WORKSPACE_SPEC,
    BenchmarkWorkspaceSpec,
)
from worldcalib.optcore.optimizer import (
    SelfDistillOptimizer,
    SelfDistillOptimizerConfig,
)
from worldcalib.schemas import LocomoExample


@dataclass(frozen=True)
class Spider2OptimizerConfig(SelfDistillOptimizerConfig):
    """Configuration for Spider2 text-to-SQL agent-policy optimization."""

    spider2_runs: int = 1
    spider2_concurrency: int = 8
    scaffolds: tuple[str, ...] = DEFAULT_SPIDER2_SEED_SCAFFOLDS


class Spider2Optimizer(SelfDistillOptimizer):
    """Proposer loop for the Spider2 agent (self-distill WMC, no external critic)."""

    workspace_spec: BenchmarkWorkspaceSpec = SPIDER2_WORKSPACE_SPEC
    config: Spider2OptimizerConfig

    def __init__(self, config: Spider2OptimizerConfig) -> None:
        super().__init__(config)

    # ── WMC note: Spider2 has no usable per-task-type axis (single "all" bucket)

    def _wmc_observability_note(self) -> str:
        return (
            ". For Spider2 there is no usable dataset task-type, so the "
            "per-category axis is a single `all` bucket; reason about failure "
            "modes from the per-task `instance_id` rows and the SQL the agent "
            "produced. Answers are graded by EXECUTING the predicted SQL against "
            "the bundled sqlite DB and comparing the result table to the gold "
            "result (column-subset match, order-insensitive unless required)"
        )

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_examples_for_split(self, split: str, limit: int = 0) -> list[LocomoExample]:
        return load_spider2_examples(split, limit=limit or 0)

    # ── evaluation ───────────────────────────────────────────────────────────

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> Spider2EvaluationRunner:
        return Spider2EvaluationRunner(
            examples=examples,
            out_dir=out_dir or self.run_dir,
            runs=self.config.spider2_runs,
            concurrency=self.config.spider2_concurrency,
        )

    # ── seed scaffold ────────────────────────────────────────────────────────

    def _build_seed_scaffold(self, name: str) -> Any:
        return build_spider2_scaffold(name)

    # ── naming / policy / candidate defaults ─────────────────────────────────

    def _benchmark_prompt_name(self) -> str:
        return "Spider2 text-to-SQL agent"

    def _raw_data_policy_name(self) -> str:
        # Name the GOLD, not "task data": the sqlite databases are not answers —
        # they are the world the query runs against, and they are mounted
        # read-only at /spider2_db precisely so assumptions about the data can be
        # checked instead of guessed. Only the gold result tables are off-limits.
        return (
            "the Spider2-lite gold result CSVs and the frozen split "
            "(the read-only databases mounted at /spider2_db ARE yours to query)"
        )

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "spider2",
            "kind": "spider2_agent",
            "scoring_method": "execution_match",
        }
