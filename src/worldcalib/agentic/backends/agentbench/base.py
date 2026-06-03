"""Agent scaffold base — the optimizable wrapper around the FC base agent.

An ``AgentScaffold`` is an agentrl ``BaseClient`` subclass: the *policy* that,
given the current conversation ``messages`` and the available ``tools``, decides
the next assistant action (the model's reply, including ``tool_calls``). It is
the agent analogue of ``MemoryScaffold`` and it is what the WorldCalib proposer
evolves.

The underlying LLM call (deepseek) is delegated to an injected ``inner`` client
that the framework binds before evaluation — the proposer does **not** edit how
the model is configured, only the *strategy* wrapped around it:

- reshape / compress / rewrite the message history before the model sees it
- augment the ``tools`` (e.g. embed environment constraints into descriptions)
- repair or validate the model's ``tool_calls`` before they go back
- add reflection / retry / self-consistency
- maintain cross-turn state on ``self`` (a fresh scaffold instance runs each
  episode, so per-episode state is safe)

The seed scaffold (``PassthroughAgentScaffold``) adds zero strategy: it forwards
``messages`` and ``tools`` straight to the base agent. That is exactly the FC
"base agent" behavior — the starting point the optimizer improves on.

The identity / config / ``fresh()`` plumbing is inherited from the
backend-agnostic :class:`ScaffoldMixin`; this module owns only the
agentrl-specific surface (``bind_inner`` / ``inner`` / ``get_model_name`` /
``close`` / ``query``) and is the only place ``agentrl`` is imported.
"""

from __future__ import annotations

from typing import Optional

from agentrl.eval.client import BaseClient
from agentrl.eval.convert import FunctionDefinition, MessageRecord

from worldcalib.optcore.scaffold_base import ScaffoldMixin
from worldcalib.scaffolds.base import ScaffoldConfig


class AgentScaffold(BaseClient, ScaffoldMixin):
    """Base class for an optimizable agent policy (an agentrl ``BaseClient``).

    Subclasses override :meth:`query` to add strategy. The default
    implementation is a pure pass-through to the bound base agent. Identity
    (``name`` / ``reference_urls``) and lifecycle (``__init__`` / ``fresh``)
    come from :class:`ScaffoldMixin`.
    """

    name: str = "agent_scaffold"
    reference_urls: tuple[str, ...] = ()

    def __init__(self, config: Optional[ScaffoldConfig] = None) -> None:
        super().__init__(config)
        self._inner: Optional[BaseClient] = None

    # ── framework plumbing (not proposer-editable behavior) ──────────────────

    def bind_inner(self, inner: BaseClient) -> "AgentScaffold":
        """Inject the underlying LLM client (deepseek). Called by the evaluator."""
        self._inner = inner
        return self

    @property
    def inner(self) -> BaseClient:
        if self._inner is None:
            raise RuntimeError(
                "AgentScaffold.inner is not bound — call bind_inner(client) before evaluation"
            )
        return self._inner

    async def get_model_name(self) -> str:
        return await self.inner.get_model_name()

    async def close(self) -> None:
        # The inner client is shared and owned by the evaluator; do not close it here.
        return None

    # ── the optimizable surface ──────────────────────────────────────────────

    async def query(
        self,
        messages: list[MessageRecord],
        tools: Optional[list[FunctionDefinition]] = None,
        cache_key: Optional[str] = None,
    ) -> list[MessageRecord]:
        """Produce the next assistant message(s) for one agent step.

        Override this to add strategy. The default is a pure pass-through to the
        base agent (forward history + tools to the model unchanged).
        """
        return await self.inner.query(messages, tools=tools, cache_key=cache_key)
