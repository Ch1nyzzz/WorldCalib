"""ARC-AGI-2 solver optimization.

Reuses the WorldCalib proposer loop to evolve an ``ArcScaffold`` (the single-shot
solver policy) instead of a memory scaffold. Uses the **self-distill WMC**
protocol shared with the tau2 / agentbench integrations: the proposer reads
``world_model_calibration.md``, self-grades its previous upside/downside
(per-task-type) prediction against the real outcome, and appends a distill
section — **no external critic** (``_score_prediction_feedback`` is a no-op).

The shared self-distill skeleton (WMC seed template, WMC seeding, no-op critic,
seed-frontier driver, example loader) lives in
:class:`worldcalib.optcore.optimizer.SelfDistillOptimizer`. This module supplies
only the ARC-specific hooks: the data split, the evaluation runner, the seed
scaffold builder, the candidate-metadata defaults, and the benchmark / data
policy names. ARC overrides the WMC Observability note (via
``_wmc_observability_note``) to describe its per-task-type axis — the output
grid-size change observed across the visible train demonstrations
(``same_size`` / ``grow`` / ``shrink`` / ``variable``). ARC **has** task-types,
so the prediction protocol stays per-task-type (not per-episode), and the
evaluation runner emits a per-category ``score_breakdown`` keyed by that axis.

Evaluation runs real ARC tasks via ``ArcEvaluationRunner`` (single shared
``LocalModelClient``, threaded over tasks, scored by exact grid match with
pass@2).

This module is agentrl-free; ARC needs only the served target model through
``worldcalib.model``, like locomo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worldcalib.benchmark_workspaces import ARC_WORKSPACE_SPEC, BenchmarkWorkspaceSpec
from worldcalib.optcore.optimizer import (
    SelfDistillOptimizer,
    SelfDistillOptimizerConfig,
)
from worldcalib.reasoning.arc_data import ARC_DEFAULT_DATA_DIR, load_arc_examples
from worldcalib.reasoning.arc_evaluation import ArcEvaluationRunner
from worldcalib.reasoning.arc_scaffolds import (
    DEFAULT_ARC_SEED_SCAFFOLDS,
    build_arc_scaffold,
)
from worldcalib.schemas import LocomoExample


@dataclass(frozen=True)
class ArcOptimizerConfig(SelfDistillOptimizerConfig):
    """Configuration for ARC-AGI-2 solver optimization."""

    # Both splits come from the ARC evaluation directory: train = first 30
    # (ordinal slice), test = remaining 90. These caps match those partition
    # sizes so the defaults use the whole partition.
    arc_data_dir: str = str(ARC_DEFAULT_DATA_DIR)
    arc_train_size: int = 30
    arc_test_size: int = 90
    arc_max_tokens: int = 2048
    arc_max_attempts: int = 2
    arc_runs: int = 1
    arc_concurrency: int = 8
    # Optimize the single-shot reasoning solver, not the agent system or the
    # MemGPT memory source.
    progressive_target_system: str = "reasoning"
    scaffolds: tuple[str, ...] = DEFAULT_ARC_SEED_SCAFFOLDS


class ArcOptimizer(SelfDistillOptimizer):
    """Proposer loop for ARC-AGI-2 solvers (self-distill WMC, no external critic)."""

    workspace_spec: BenchmarkWorkspaceSpec = ARC_WORKSPACE_SPEC
    config: ArcOptimizerConfig

    def __init__(self, config: ArcOptimizerConfig) -> None:
        super().__init__(config)

    # ── per-backend WMC note ──────────────────────────────────────────────────

    def _wmc_observability_note(self) -> str:
        """Describe ARC's per-task-type axis for the WMC Observability bullet.

        ARC's ``score_breakdown`` task-type is the output grid-size change
        observed across the visible train demonstrations.
        """
        return (
            ". For ARC the task-type is the output grid-size change observed "
            "across the visible train demonstrations: `same_size` (output area "
            "== input area), `grow` (output larger), `shrink` (output smaller), "
            "or `variable` (mixed across demonstrations)"
        )

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_examples_for_split(
        self, split: str, limit: int = 0
    ) -> list[LocomoExample]:
        return load_arc_examples(
            self.config.arc_data_dir,
            split,
            train_size=self.config.arc_train_size,
            test_size=self.config.arc_test_size,
            limit=limit or 0,
        )

    # ── evaluation ───────────────────────────────────────────────────────────

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> ArcEvaluationRunner:
        return ArcEvaluationRunner(
            examples=examples,
            out_dir=out_dir or self.run_dir,
            model=self.config.model,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout_s=self.config.eval_timeout_s,
            max_tokens=self.config.arc_max_tokens,
            max_attempts=self.config.arc_max_attempts,
            runs=self.config.arc_runs,
            concurrency=self.config.arc_concurrency,
        )

    # ── seed scaffold ─────────────────────────────────────────────────────────

    def _build_seed_scaffold(self, name: str):
        return build_arc_scaffold(name)

    # ── naming / policy / candidate defaults ─────────────────────────────────

    def _benchmark_prompt_name(self) -> str:
        return "arc-agi-2 reasoning solver"

    def _raw_data_policy_name(self) -> str:
        return "raw ARC-AGI-2 task grids"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "arc_agi2",
            "kind": "arc_solver",
            "scoring_method": "grid_passat2",
        }
