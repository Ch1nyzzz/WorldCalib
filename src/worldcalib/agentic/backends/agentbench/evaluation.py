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

# Head-truncate / tail-keep budget for the rendered rollout (same policy as
# tau2's render_transcript): a webshop product listing is long, but the
# episode's outcome — what the agent finally bought and its reward — is at the
# tail, so we keep the tail. The task instruction lives at the head and is
# extracted separately into `question`, so head-truncation does not lose it.
_MAX_TRANSCRIPT_CHARS = 12000


def _flatten_content(content: Any) -> str:
    """OpenAI chat ``content`` is either a string or a list of typed parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(str(part["text"]))
                elif part.get("type") == "image_url":
                    parts.append("<image>")
            elif part:
                parts.append(str(part))
        return "\n".join(parts)
    return str(content)


def _extract_instruction(raw_trace: Any) -> str:
    """The task the episode was asked to do.

    AgentBench examples are index-only (``question=""``); the real task text is
    served at runtime as the first *user* observation (webshop: ``WebShop [SEP]
    Instruction: [SEP] <task> [SEP] Search``; os: the problem statement). Return
    it verbatim so the proposer diagnoses the actual task, not ``webshop#3``.
    """
    for msg in raw_trace or []:
        if isinstance(msg, dict) and msg.get("role") == "user":
            text = _flatten_content(msg.get("content")).strip()
            if text:
                return text
    return ""


def _render_transcript(raw_trace: Any) -> str:
    """The episode's full rollout — the candidate's actual behavior.

    ``reward=0.0`` says the episode failed; only the transcript says whether the
    agent searched the wrong keywords, clicked the wrong product, or bought one
    that missed a required attribute. Tool calls (search/click) are rendered
    inline because that is where webshop/os episodes actually go wrong.
    """
    lines: list[str] = []
    for msg in raw_trace or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "?"))
        text = _flatten_content(msg.get("content"))
        if text:
            lines.append(f"[{role}] {text}")
        # Reasoning-model transcripts (the served deepseek-v4-flash emits one)
        # carry the agent's chain-of-thought here; it is where a wrong click is
        # actually reasoned out, so it is diagnostic evidence, not chatter.
        reasoning = msg.get("reasoning_content")
        if reasoning:
            lines.append(f"[{role} thinking] {reasoning}")
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") if isinstance(call, dict) else None
            fn = fn or {}
            lines.append(f"[{role} tool_call] {fn.get('name', '?')}({fn.get('arguments', '')})")
    if not lines:
        return "(no messages)"
    text = "\n".join(lines)
    if len(text) <= _MAX_TRANSCRIPT_CHARS:
        return text
    return "... (head truncated, tail kept) ...\n" + text[-_MAX_TRANSCRIPT_CHARS:]


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
        temperature: float = 0.0,
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
        self.temperature = temperature
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
            # agentrl defaults to 0.8; pin it (0.0 by default) so episode
            # outcomes are as deterministic as the serving stack allows and
            # iter-to-iter per-task flips reflect the candidate, not sampling.
            temperature=self.temperature,
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

        # The rollout: the served task text (instruction), the full action
        # trace, and the episode's outcome. Previously the record kept only
        # `status` — a tally that could not distinguish a wrong-product buy from
        # a search that never converged, so a failed episode read as uncaused.
        raw_trace = getattr(result, "raw_trace", None)
        instruction = _extract_instruction(raw_trace)
        transcript = _render_transcript(raw_trace)
        transcript = f"{transcript}\n\n[episode end] status={result.status} reward={reward}"

        return TaskResult(
            task_id=example.task_id,
            # index-only examples carry no question; recover the served task text
            # from the rollout, falling back to task_id only if the trace is empty.
            question=instruction or example.task_id,
            # WebShop scores a continuous attribute match, not a single gold
            # string: the required attributes are stated in the instruction
            # (now in `question`) and the server's reward/attribute breakdown,
            # when present, rides in metadata (server_result / task_trace). We do
            # not fabricate a gold answer the benchmark does not define.
            gold_answer="",
            prediction=transcript,
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
                # Server-side outcome carried verbatim (faithful translator, not
                # diagnostician): result may hold the task-type / target attrs;
                # task_trace holds the reward breakdown when the worker emits one.
                "server_result": result.result,
                "task_trace": getattr(result, "task_trace", None),
            },
        )
