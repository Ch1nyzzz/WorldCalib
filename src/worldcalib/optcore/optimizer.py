"""Shared self-distill optimizer skeleton for agent-policy benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import LocomoExample


@dataclass(frozen=True)
class SelfDistillOptimizerConfig(OptimizerConfig):
    """Shared configuration base for self-distill (agent-policy) optimization."""

    # Optimize the agent-policy scaffold, not the MemGPT memory source.
    progressive_target_system: str = "agent"
    scaffolds: tuple[str, ...] = ()


class SelfDistillOptimizer(LocomoOptimizer):
    """Shared proposer loop for agent backends (self-distill WMC, no critic)."""

    config: SelfDistillOptimizerConfig

    # ── per-backend WMC note hook ─────────────────────────────────────────────

    def _wmc_observability_note(self) -> str:
        """Extra text spliced into the WMC Observability per-category bullet.

        Default empty; benchmark subclasses may describe their task-type axis.
        """
        return ""

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_examples(self) -> list[LocomoExample]:
        return self._load_examples_for_split(self.config.split, self.config.limit)

    # ── seed frontier: evaluate the pass-through seed scaffold(s) ─────────────

    def _run_seed_frontier(self) -> dict[str, Any]:
        examples = self._load_examples()
        runner = self._make_evaluation_runner(examples)
        candidates: list[dict[str, Any]] = []
        for name in self.config.scaffolds:
            scaffold = self._build_seed_scaffold(name)
            config = ScaffoldConfig(extra=dict(self._candidate_extra_defaults()))
            result = runner.evaluate_scaffold(
                scaffold=scaffold,
                scaffold_name=name,
                config=config,
                candidate_id=f"iter000_{name}",
            )
            candidates.append(result.to_dict())
        self._seed_world_model_calibration()
        return {"candidates": candidates}

    # NOTE: the base ``_score_prediction_feedback`` is hidden mechanical
    # telemetry only (no LLM critic, never staged into a workspace), so the
    # self-distill protocol holds without an override here.

    # ── abstract hooks each backend implements ────────────────────────────────

    def _load_examples_for_split(self, split: str, limit: int = 0) -> list[LocomoExample]:
        raise NotImplementedError

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> Any:
        raise NotImplementedError

    def _build_seed_scaffold(self, name: str) -> Any:
        raise NotImplementedError

    def _candidate_extra_defaults(self) -> dict[str, object]:
        raise NotImplementedError

    def _benchmark_prompt_name(self) -> str:
        raise NotImplementedError

    def _raw_data_policy_name(self) -> str:
        raise NotImplementedError
