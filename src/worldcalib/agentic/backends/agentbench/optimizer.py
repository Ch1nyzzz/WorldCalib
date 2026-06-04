"""AgentBench agent-policy optimization.

Reuses the shared self-distill proposer loop (:class:`SelfDistillOptimizer`) to
evolve an ``AgentScaffold`` (the FC agent policy) instead of a memory scaffold.
Uses the
**self-distill WMC** protocol: the proposer reads ``world_model_calibration.md``,
self-grades its previous upside/downside (per-task-type) prediction against the
real outcome, and appends a distill section — **no external critic**.

Evaluation runs real AgentBench episodes via ``AgentEvaluationRunner`` and emits
a per-category (task-type) ``score_breakdown`` so the prediction protocol works
unchanged. This module narrows the shared base to the AgentBench-specific
concerns: the controller/task config fields, the example loader, the evaluation
runner, the seed scaffold builder, and the candidate metadata defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from worldcalib.agentic.backends.agentbench import (
    DEFAULT_AGENT_SEED_SCAFFOLDS,
    build_agent_scaffold,
)
from worldcalib.agentic.backends.agentbench.base import AgentScaffold
from worldcalib.agentic.backends.agentbench.data import load_agentbench_examples
from worldcalib.agentic.backends.agentbench.evaluation import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    AgentEvaluationRunner,
)
from worldcalib.optcore.optimizer import (
    SelfDistillOptimizer,
    SelfDistillOptimizerConfig,
)
from worldcalib.benchmark_workspaces import AGENTBENCH_WORKSPACE_SPEC, BenchmarkWorkspaceSpec
from worldcalib.schemas import LocomoExample


@dataclass(frozen=True)
class AgentBenchOptimizerConfig(SelfDistillOptimizerConfig):
    """Configuration for AgentBench agent-policy optimization."""

    agentbench_task: str = "db"
    controller_url: str = "http://localhost:5020/api"
    agentbench_runs: int = 1
    agentbench_concurrency: int = 8
    # Small by default (30): no-task-type tasks (os/webshop/alfworld) are
    # predicted per episode, tractable only at a small episode count.
    agentbench_train_size: int = 30
    agentbench_test_size: int = 40
    agentbench_pass_threshold: float = 1.0
    deepseek_model: str = DEFAULT_DEEPSEEK_MODEL
    deepseek_base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    scaffolds: tuple[str, ...] = DEFAULT_AGENT_SEED_SCAFFOLDS


class AgentBenchOptimizer(SelfDistillOptimizer):
    """Proposer loop for AgentBench agents (self-distill WMC, no external critic)."""

    workspace_spec: BenchmarkWorkspaceSpec = AGENTBENCH_WORKSPACE_SPEC
    config: AgentBenchOptimizerConfig

    def __init__(self, config: AgentBenchOptimizerConfig) -> None:
        super().__init__(config)

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_examples_for_split(self, split: str, limit: int = 0) -> list[LocomoExample]:
        return load_agentbench_examples(
            self.config.agentbench_task,
            split,
            controller_url=self.config.controller_url,
            train_size=self.config.agentbench_train_size,
            test_size=self.config.agentbench_test_size,
            limit=limit or 0,
        )

    # ── evaluation ───────────────────────────────────────────────────────────

    def _deepseek_api_key(self) -> str:
        key = self.config.api_key
        if not key or key == "EMPTY":
            key = os.environ.get("DEEPSEEK_API_KEY", "")
        return key

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> AgentEvaluationRunner:
        return AgentEvaluationRunner(
            examples=examples,
            out_dir=out_dir or self.run_dir,
            controller_url=self.config.controller_url,
            task=self.config.agentbench_task,
            model=self.config.deepseek_model,
            base_url=self.config.deepseek_base_url,
            api_key=self._deepseek_api_key(),
            runs=self.config.agentbench_runs,
            concurrency=self.config.agentbench_concurrency,
            pass_threshold=self.config.agentbench_pass_threshold,
        )

    # ── seed scaffold ─────────────────────────────────────────────────────────

    def _build_seed_scaffold(self, name: str) -> AgentScaffold:
        return build_agent_scaffold(name)

    def _probe_rejects_on_zero_completion_tokens(self) -> bool:
        """AgentBench rows hardcode 0 tokens (the agentrl client never surfaces
        usage), so zero completion tokens is NOT a crash signal here — it is the
        norm for every candidate, including the working seed. The dry-run probe
        keeps only its raised-exception detection for this backend.
        """
        return False

    # ── naming / policy / candidate defaults ─────────────────────────────────

    def _benchmark_prompt_name(self) -> str:
        return f"AgentBench {self.config.agentbench_task} agent"

    def _raw_data_policy_name(self) -> str:
        return "raw AgentBench task data"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "agentbench",
            "task": self.config.agentbench_task,
            "kind": "agent",
            "scoring_method": "episode_reward",
        }
