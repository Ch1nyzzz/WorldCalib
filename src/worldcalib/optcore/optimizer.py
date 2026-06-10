"""Shared self-distill optimizer skeleton.

``SelfDistillOptimizer`` holds the parts the two backend optimizers
(``AgentBenchOptimizer``, ``Tau2Optimizer``) share verbatim: the self-distill
World Model Calibration (WMC) seed template, the WMC seeding, the no-op
prediction critic (self-distill protocol — the proposer grades its own
prediction next iter), the seed-frontier driver, and the example loader. Each
backend subclass implements only the small set of abstract hooks that name its
benchmark, build its evaluation runner, build its seed scaffold, and supply its
candidate metadata defaults.

``SelfDistillOptimizerConfig`` is the shared config base: it targets the agent
system (``progressive_target_system = "agent"``) rather than the MemGPT memory
source.

This module imports neither ``agentrl`` nor ``tau2`` at top level; the backend
subclasses inject those concerns through the abstract hooks.
"""

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

    # The self-distill WMC seed. The Observability section embeds a per-backend
    # note (via ``_wmc_observability_note``) so e.g. tau2 can explain that its
    # task-type category is the task's ``reward_basis`` signature.
    _WMC_SEED_TEMPLATE = """# World Model Calibration

Append-only. The proposer reads this file before reasoning about the next
candidate, **self-grades** the previous iter's upside/downside prediction
against the real per-category outcome, then appends a new
`## iter_PREV -> iter_THIS distill` section. Never rewrite or delete prior
entries.

## Observability

Each iter produces, per candidate:
- overall train passrate + average reward
- the per-category units your prediction's Upside/Downside lists are measured
  against: the `score_breakdown` task-types when the dataset defines them, else
  the per-episode `score`/`passed` rows in `candidate_results/<id>.json`
  `tasks[]` (predict per episode `task_id`){observability_note}
- episode traces

There is no external critic and no hidden score: you grade your own prediction.
Only write claims the next iter's measurements could disconfirm.
"""

    config: SelfDistillOptimizerConfig

    # ── per-backend WMC note hook ─────────────────────────────────────────────

    def _wmc_observability_note(self) -> str:
        """Extra text spliced into the WMC Observability per-category bullet.

        Default empty; tau2 overrides it to describe its ``reward_basis``
        task-type signature.
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

    def _seed_world_model_calibration(self) -> None:
        """Seed the self-distill WMC file so the first proposer iter can read it."""
        path = self.run_dir / "world_model_calibration.md"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            text = self._WMC_SEED_TEMPLATE.format(
                observability_note=self._wmc_observability_note()
            )
            path.write_text(text, encoding="utf-8")

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
