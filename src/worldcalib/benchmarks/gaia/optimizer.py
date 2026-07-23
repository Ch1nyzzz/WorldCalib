"""GAIA agent-policy optimization.

Reuses the WorldCalib self-distill proposer loop to evolve a ``GaiaScaffold``
(the GAIA agent's FC policy) — same protocol as the other agentic backends:
the proposer reads ``world_model_calibration.md``, self-grades its previous
prediction against the real outcome, and appends a distill section — **no
external critic**.

Evaluation runs real GAIA episodes via :class:`GaiaEvaluationRunner` (the FC
loop over the locked DeepSeek SUT, exact-match scored), emitting a per-category
``score_breakdown`` keyed by GAIA ``level`` (``level_1`` …) so the prediction
protocol works unchanged.

The shared seed-frontier driver, WMC seeding, no-op critic, and example loader
live in :class:`SelfDistillOptimizer`; this module supplies only the
GAIA-specific hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.benchmarks.gaia import (
    DEFAULT_GAIA_SEED_SCAFFOLDS,
    build_gaia_scaffold,
)
from worldcalib.benchmarks.gaia.data import DEFAULT_LEVELS, load_gaia_examples
from worldcalib.benchmarks.gaia.evaluation import GaiaEvaluationRunner
from worldcalib.benchmark_workspaces import GAIA_WORKSPACE_SPEC, BenchmarkWorkspaceSpec
from worldcalib.optcore.optimizer import (
    SelfDistillOptimizer,
    SelfDistillOptimizerConfig,
)
from worldcalib.schemas import LocomoExample


@dataclass(frozen=True)
class GaiaOptimizerConfig(SelfDistillOptimizerConfig):
    """Configuration for GAIA agent-policy optimization."""

    gaia_levels: tuple[int, ...] = DEFAULT_LEVELS
    gaia_runs: int = 1
    gaia_concurrency: int = 8
    gaia_train_size: int = 40
    gaia_test_size: int = 99
    scaffolds: tuple[str, ...] = DEFAULT_GAIA_SEED_SCAFFOLDS


class GaiaOptimizer(SelfDistillOptimizer):
    """Proposer loop for the GAIA agent (self-distill WMC, no external critic)."""

    workspace_spec: BenchmarkWorkspaceSpec = GAIA_WORKSPACE_SPEC
    config: GaiaOptimizerConfig

    def __init__(self, config: GaiaOptimizerConfig) -> None:
        super().__init__(config)

    # ── WMC note: GAIA's task-type category is the difficulty level ───────────

    def _wmc_observability_note(self) -> str:
        return (
            ". For GAIA the task-type is the task's difficulty `level` "
            "(`level_1`, `level_2`); answers are graded by exact match against "
            "the gold answer"
        )

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_examples_for_split(self, split: str, limit: int = 0) -> list[LocomoExample]:
        return load_gaia_examples(
            split,
            levels=self.config.gaia_levels,
            train_size=self.config.gaia_train_size,
            test_size=self.config.gaia_test_size,
            limit=limit or 0,
        )

    # ── evaluation ───────────────────────────────────────────────────────────

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> GaiaEvaluationRunner:
        return GaiaEvaluationRunner(
            examples=examples,
            out_dir=out_dir or self.run_dir,
            runs=self.config.gaia_runs,
            concurrency=self.config.gaia_concurrency,
        )

    # ── seed scaffold ────────────────────────────────────────────────────────

    def _build_seed_scaffold(self, name: str) -> Any:
        return build_gaia_scaffold(name)

    # ── naming / policy / candidate defaults ─────────────────────────────────

    def _benchmark_prompt_name(self) -> str:
        return "GAIA agent"

    def _raw_data_policy_name(self) -> str:
        return "raw GAIA task data"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "gaia",
            "kind": "gaia_agent",
            "scoring_method": "exact_match",
        }
