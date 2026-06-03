"""Agent evaluation runner — score an AgentScaffold over real AgentBench episodes.

Unlike the memory-QA ``EvaluationRunner`` (pure build+answer, cached, threaded),
agent scaffolds are stateful multi-turn policies evaluated against a live
controller. This runner drives ``agentrl.eval``'s ``SampleWorkflow`` directly
(one fresh scaffold per episode, a shared deepseek client underneath), collects
each episode's ``reward``, and aggregates a ``CandidateResult`` plus a
``candidate_results/<id>.json`` payload with a **per-category score_breakdown**
keyed by task-type — the interface the self-distill prediction protocol reads.

It exposes the same ``evaluate_scaffold(...)`` signature the optimizer main loop
calls, so the proposer/iteration framework is reused unchanged. The failed-row
and candidate-summary shaping are delegated to the shared
:mod:`worldcalib.optcore.evaluation` helpers; this module owns only the agentrl
``SampleWorkflow`` episode execution (the only place ``agentrl`` is imported).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from agentrl.eval.client import OpenAIClient, OpenAIOptions
from agentrl.eval.session.controller import ControllerClient
from agentrl.eval.session.types import RunSpec
from agentrl.eval.session.workflow import SampleWorkflow

from worldcalib.agentic.backends.agentbench.base import AgentScaffold
from worldcalib.agentic.backends.agentbench.data import task_server_name
from worldcalib.optcore.evaluation import build_error_task_result, summarize_candidate
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


class AgentEvaluationRunner:
    """Evaluate an ``AgentScaffold`` over a task's train/test split of episodes."""

    def __init__(
        self,
        *,
        examples: list[LocomoExample],
        out_dir: Path,
        controller_url: str,
        task: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        api_key: str = "",
        runs: int = 1,
        concurrency: int = 8,
        pass_threshold: float = 1.0,
        insecure: bool = False,
    ) -> None:
        self.examples = examples
        self.out_dir = Path(out_dir)
        self.controller_url = controller_url
        self.task = task
        self.server = task_server_name(task)
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.runs = max(1, runs)
        self.concurrency = max(1, concurrency)
        self.pass_threshold = pass_threshold
        self.insecure = insecure

    # ── inner deepseek client (the base agent's LLM call) ────────────────────

    def _make_inner(self) -> OpenAIClient:
        opts = OpenAIOptions(
            model=self.model,
            api_key=SecretStr(self.api_key) if self.api_key else None,
            base_url=self.base_url,
            thinking=False,
            chat_completions=True,
            parallel_tool_calls=False,
            insecure=self.insecure,
        )
        return OpenAIClient(opts, token_counter=None)

    # ── public API (matches the optimizer main loop) ─────────────────────────

    def evaluate_scaffold(
        self,
        *,
        scaffold: AgentScaffold,
        scaffold_name: str,
        config: ScaffoldConfig,
        candidate_id: str,
    ) -> CandidateResult:
        task_results = asyncio.run(self._run_all(scaffold, scaffold_name))
        return summarize_candidate(
            task_results=task_results,
            scaffold_name=scaffold_name,
            config=config,
            candidate_id=candidate_id,
            out_dir=self.out_dir,
        )

    # ── episode execution ────────────────────────────────────────────────────

    async def _run_all(
        self, scaffold: AgentScaffold, scaffold_name: str
    ) -> list[TaskResult]:
        controller = ControllerClient(
            base_url=self.controller_url, proxy_url=None, insecure=self.insecure
        )
        inner = self._make_inner()
        sem = asyncio.Semaphore(self.concurrency)

        async def run_one(example: LocomoExample, run_idx: int):
            async with sem:
                try:
                    episode_scaffold = scaffold.fresh().bind_inner(inner)
                    spec = RunSpec(
                        model=scaffold_name,
                        run=run_idx,
                        task=self.server,
                        index=example.metadata["index"],
                        custom_params=None,
                    )
                    workflow = SampleWorkflow(
                        controller=controller, models=[episode_scaffold], spec=spec
                    )
                    return example, await workflow()
                except Exception as exc:  # isolate a single episode failure → score 0
                    return example, exc

        jobs = [
            run_one(example, run_idx)
            for run_idx in range(self.runs)
            for example in self.examples
        ]
        try:
            pairs = await asyncio.gather(*jobs)
        finally:
            await inner.close()
            await controller.close()

        return [self._to_task_result(example, result) for example, result in pairs]

    def _to_task_result(self, example: LocomoExample, result: Any) -> TaskResult:
        if isinstance(result, BaseException):
            # A single episode raised (e.g. deepseek 400 on a dangling tool_call
            # the seed scaffold did not repair). Score it 0 and keep going — never
            # let one bad episode crash the whole batch.
            return build_error_task_result(
                example,
                error=str(result)[:300],
                status="client_error",
                index=example.metadata["index"],
            )
        reward = result.reward if result.reward is not None else 0.0
        score = float(reward)
        passed = score >= self.pass_threshold

        # task-type category: prefer the episode's own result (DB returns "type"),
        # else any pre-built question_type on the example, else "all".
        category = None
        if isinstance(result.result, dict):
            category = result.result.get("type")
        question_type = str(category or example.metadata.get("question_type") or "all")

        return TaskResult(
            task_id=example.task_id,
            question=example.task_id,
            gold_answer="",
            prediction=str(result.status),
            score=score,
            passed=passed,
            prompt_tokens=0,
            completion_tokens=0,
            retrieved=[],
            metadata={
                "question_type": question_type,
                "status": str(result.status),
                "index": example.metadata["index"],
                "reward": reward,
            },
        )
