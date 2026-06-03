"""tau2 agent-policy optimization.

Reuses the WorldCalib proposer loop to evolve a ``Tau2Scaffold`` (the tau2 agent
policy) instead of a memory scaffold. Uses the **self-distill WMC** protocol
shared by every agentic backend: the proposer reads
``world_model_calibration.md``, self-grades its previous upside/downside
(per-task-type) prediction against the real outcome, and appends a distill
section — **no external critic** (``_score_prediction_feedback`` is a no-op,
inherited from :class:`SelfDistillOptimizer`).

Evaluation runs real tau2 episodes via ``Tau2EvaluationRunner`` (agent + deepseek
user simulator + stateful environment, scored by ``reward_info.reward``) and
emits a per-category (task-type) ``score_breakdown`` keyed by each task's
``reward_basis`` signature, so the prediction protocol works unchanged.

The shared seed-frontier driver, WMC seeding, no-op critic, and example loader
live in :class:`SelfDistillOptimizer`; this module supplies only the tau2-specific
hooks (data split, evaluation runner, seed scaffold, naming, candidate
metadata defaults, and the reward-basis WMC observability note). ``tau2`` is not
imported at module top level — only ``data`` / ``evaluation`` (tau2 backend
modules) are, which themselves import tau2; this module therefore loads only in
a tau2-capable venv but never pulls agentrl.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.agentic.backends.tau2 import (
    DEFAULT_TAU2_SEED_SCAFFOLDS,
    build_tau2_scaffold,
)
from worldcalib.agentic.backends.tau2.data import load_tau2_examples
from worldcalib.agentic.backends.tau2.evaluation import (
    DEFAULT_TAU2_AGENT_MODEL,
    DEFAULT_TAU2_MAX_STEPS,
    DEFAULT_TAU2_USER_MODEL,
    Tau2EvaluationRunner,
)
from worldcalib.optcore.optimizer import (
    SelfDistillOptimizer,
    SelfDistillOptimizerConfig,
)
from worldcalib.benchmark_workspaces import TAU2_WORKSPACE_SPEC, BenchmarkWorkspaceSpec
from worldcalib.schemas import LocomoExample


@dataclass(frozen=True)
class Tau2OptimizerConfig(SelfDistillOptimizerConfig):
    """Configuration for tau2 agent-policy optimization."""

    tau2_domain: str = "telecom"
    tau2_agent_model: str = DEFAULT_TAU2_AGENT_MODEL
    tau2_user_model: str = DEFAULT_TAU2_USER_MODEL
    tau2_agent_temperature: float = 0.0
    tau2_user_temperature: float = 0.0
    tau2_max_steps: int = DEFAULT_TAU2_MAX_STEPS
    tau2_runs: int = 1
    tau2_concurrency: int = 4
    tau2_train_size: int = 40
    tau2_test_size: int = 40
    tau2_pass_threshold: float = 1.0
    tau2_request_timeout_s: int = 120
    tau2_num_retries: int = 2
    scaffolds: tuple[str, ...] = DEFAULT_TAU2_SEED_SCAFFOLDS


class Tau2Optimizer(SelfDistillOptimizer):
    """Proposer loop for tau2 agents (self-distill WMC, no external critic)."""

    workspace_spec: BenchmarkWorkspaceSpec = TAU2_WORKSPACE_SPEC
    config: Tau2OptimizerConfig

    def __init__(self, config: Tau2OptimizerConfig) -> None:
        super().__init__(config)

    # ── WMC note: tau2's task-type category is the reward_basis signature ─────

    def _wmc_observability_note(self) -> str:
        return (
            ". For tau2 the task-type is the task's `reward_basis` signature "
            "(e.g. `ENV_ASSERTION`, `ACTION+ENV_ASSERTION`, `DB+COMMUNICATE`)"
        )

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_examples_for_split(self, split: str, limit: int = 0) -> list[LocomoExample]:
        return load_tau2_examples(
            self.config.tau2_domain,
            split,
            train_size=self.config.tau2_train_size,
            test_size=self.config.tau2_test_size,
            limit=limit or 0,
        )

    # ── evaluation ───────────────────────────────────────────────────────────

    def _llm_args(self, temperature: float) -> dict[str, Any]:
        return {
            "temperature": temperature,
            "num_retries": self.config.tau2_num_retries,
            "timeout": self.config.tau2_request_timeout_s,
        }

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> Tau2EvaluationRunner:
        return Tau2EvaluationRunner(
            examples=examples,
            out_dir=out_dir or self.run_dir,
            domain=self.config.tau2_domain,
            agent_model=self.config.tau2_agent_model,
            user_model=self.config.tau2_user_model,
            agent_llm_args=self._llm_args(self.config.tau2_agent_temperature),
            user_llm_args=self._llm_args(self.config.tau2_user_temperature),
            max_steps=self.config.tau2_max_steps,
            runs=self.config.tau2_runs,
            concurrency=self.config.tau2_concurrency,
            pass_threshold=self.config.tau2_pass_threshold,
        )

    # ── seed scaffold ────────────────────────────────────────────────────────

    def _build_seed_scaffold(self, name: str) -> Any:
        return build_tau2_scaffold(name)

    # ── naming / policy / candidate defaults ─────────────────────────────────

    def _benchmark_prompt_name(self) -> str:
        return f"tau2 {self.config.tau2_domain} agent"

    def _raw_data_policy_name(self) -> str:
        return "raw tau2 task data"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "tau2",
            "domain": self.config.tau2_domain,
            "kind": "tau2_agent",
            "scoring_method": "episode_reward",
        }
