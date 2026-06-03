"""tau2 evaluation runner — score a ``Tau2Scaffold`` over real tau2 episodes.

Unlike the memory-QA ``EvaluationRunner`` (pure build+answer, cached, threaded),
a tau2 agent is a stateful multi-turn policy evaluated against a live
``Orchestrator`` that also drives a (deepseek) user simulator and a stateful
environment. This runner builds a **fresh** environment / agent / user /
orchestrator per episode (the domain DB is mutated during a run, so episodes
must not share env state), runs ``tau2.runner.simulation.run_simulation``,
collects each episode's ``reward_info.reward``, and aggregates a
``CandidateResult`` plus a ``candidate_results/<id>.json`` payload with a
**per-category score_breakdown** keyed by ``question_type`` (the task's
``reward_basis`` signature) — the interface the self-distill prediction protocol
reads.

It exposes the same ``evaluate_scaffold(...)`` signature the optimizer main loop
calls, so the proposer/iteration framework is reused unchanged. Episodes run on
a ``ThreadPoolExecutor`` (tau2's ``run_simulation`` + litellm calls are
synchronous and blocking, so threads give the concurrency).

The per-episode failure row and the candidate summary are delegated to the
shared :mod:`worldcalib.optcore.evaluation` helpers
(``build_error_task_result`` / ``summarize_candidate``) so the agentbench and
tau2 runners share one summary/error shape; only the tau2-specific episode
execution lives here. ``tau2`` is imported in this module (tau2 backend).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from tau2.agent.llm_agent import LLMAgent
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.registry import registry
from tau2.runner.simulation import run_simulation
from tau2.user.user_simulator import UserSimulator

from worldcalib.agentic.backends.tau2.base import Tau2Scaffold
from worldcalib.optcore.evaluation import build_error_task_result, summarize_candidate
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample, TaskResult

DEFAULT_TAU2_AGENT_MODEL = "deepseek/deepseek-chat"
DEFAULT_TAU2_USER_MODEL = "deepseek/deepseek-chat"
DEFAULT_TAU2_MAX_STEPS = 200


def _usage_get(usage: Any, key: str) -> int:
    """Read a token count from tau2's ``usage`` (an Optional[dict], but be lenient)."""
    if isinstance(usage, dict):
        return int(usage.get(key) or 0)
    return int(getattr(usage, key, 0) or 0)


def _sum_tokens(simulation: Any) -> tuple[int, int]:
    """Best-effort (prompt, completion) token totals over a simulation run."""
    prompt = completion = 0
    for msg in getattr(simulation, "messages", None) or []:
        usage = getattr(msg, "usage", None)
        if not usage:
            continue
        prompt += _usage_get(usage, "prompt_tokens")
        completion += _usage_get(usage, "completion_tokens")
    return prompt, completion


class Tau2EvaluationRunner:
    """Evaluate a ``Tau2Scaffold`` over a domain's train/test split of episodes."""

    def __init__(
        self,
        *,
        examples: list[LocomoExample],
        out_dir: Path,
        domain: str,
        agent_model: str = DEFAULT_TAU2_AGENT_MODEL,
        user_model: str = DEFAULT_TAU2_USER_MODEL,
        agent_llm_args: Optional[dict[str, Any]] = None,
        user_llm_args: Optional[dict[str, Any]] = None,
        max_steps: int = DEFAULT_TAU2_MAX_STEPS,
        runs: int = 1,
        concurrency: int = 4,
        pass_threshold: float = 1.0,
    ) -> None:
        self.examples = examples
        self.out_dir = Path(out_dir)
        self.domain = domain
        self.agent_model = agent_model
        self.user_model = user_model
        self.agent_llm_args = dict(agent_llm_args or {"temperature": 0.0})
        self.user_llm_args = dict(user_llm_args or {"temperature": 0.0})
        self.max_steps = max_steps
        self.runs = max(1, runs)
        self.concurrency = max(1, concurrency)
        self.pass_threshold = pass_threshold
        self._tasks_by_id = {t.id: t for t in registry.get_tasks_loader(domain)()}

    # ── public API (matches the optimizer main loop) ─────────────────────────

    def evaluate_scaffold(
        self,
        *,
        scaffold: Tau2Scaffold,
        scaffold_name: str,
        config: ScaffoldConfig,
        candidate_id: str,
    ) -> CandidateResult:
        task_results = self._run_all(scaffold)
        return self._summarize(task_results, scaffold_name, config, candidate_id)

    # ── episode execution ────────────────────────────────────────────────────

    def _run_all(self, scaffold: Tau2Scaffold) -> list[TaskResult]:
        jobs = [
            (example, run_idx)
            for run_idx in range(self.runs)
            for example in self.examples
        ]
        results: list[TaskResult] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._run_one, scaffold, example, run_idx): example
                for example, run_idx in jobs
            }
            for future in as_completed(futures):
                example = futures[future]
                simulation, error = future.result()
                results.append(self._to_task_result(example, simulation, error))
        return results

    def _build_agent(self, scaffold: Tau2Scaffold, env: Any) -> LLMAgent:
        return scaffold.fresh().build_agent(
            tools=env.get_tools(),
            domain_policy=env.get_policy(),
            llm=self.agent_model,
            llm_args=dict(self.agent_llm_args),
        )

    def _run_one(
        self, scaffold: Tau2Scaffold, example: LocomoExample, run_idx: int
    ) -> tuple[Any, Optional[str]]:
        """Run one episode. Returns (simulation_run, error_str). Never raises."""
        try:
            task = self._tasks_by_id[example.metadata["task_id"]]
            env = registry.get_env_constructor(self.domain)(solo_mode=False)
            try:
                user_tools = env.get_user_tools(include=task.user_tools) or None
            except ValueError:
                user_tools = None
            agent = self._build_agent(scaffold, env)
            user = UserSimulator(
                tools=user_tools,
                instructions=task.user_scenario,
                llm=self.user_model,
                llm_args=dict(self.user_llm_args),
            )
            orchestrator = Orchestrator(
                domain=self.domain,
                agent=agent,
                user=user,
                environment=env,
                task=task,
                max_steps=self.max_steps,
            )
            return run_simulation(orchestrator), None
        except Exception as exc:  # noqa: BLE001 — one bad episode must not kill the eval
            return None, f"{type(exc).__name__}: {exc}"

    def _to_task_result(
        self, example: LocomoExample, simulation: Any, error: Optional[str]
    ) -> TaskResult:
        question_type = str(example.metadata.get("question_type") or "all")

        if simulation is None:
            return build_error_task_result(
                example,
                error=error or "unknown error",
                status="error",
                domain=self.domain,
            )

        reward_info = getattr(simulation, "reward_info", None)
        reward = getattr(reward_info, "reward", None)
        score = float(reward) if reward is not None else 0.0
        passed = score >= self.pass_threshold
        prompt_tokens, completion_tokens = _sum_tokens(simulation)
        breakdown = (
            reward_info.reward_breakdown
            if reward_info is not None and getattr(reward_info, "reward_breakdown", None)
            else None
        )

        return TaskResult(
            task_id=example.task_id,
            question=example.task_id,
            gold_answer="",
            prediction=f"reward={score}",
            score=score,
            passed=passed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            retrieved=[],
            metadata={
                "question_type": question_type,
                "status": "completed",
                "reward": reward,
                "reward_breakdown": breakdown,
                "num_messages": len(getattr(simulation, "messages", None) or []),
                "domain": self.domain,
            },
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
