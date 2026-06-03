"""Tau2 agent scaffold base — the optimizable wrapper around the tau2 agent.

A ``Tau2Scaffold`` is the policy that, given a tau2 task's tools and domain
policy, builds the **agent** that converses with the (simulated) user and acts
on the environment. It is the tau2 analogue of ``MemoryScaffold`` /
``AgentScaffold`` and it is what the WorldCalib proposer evolves.

Unlike the AgentBench ``AgentScaffold`` (an agentrl ``BaseClient`` whose
``query`` is driven by agentrl's workflow), a tau2 agent is driven by tau2's
``Orchestrator`` through ``generate_next_message(message, state)`` and the LLM
call goes through tau2's ``generate()`` (litellm). So the optimizable seam here
is a **factory** that returns a ``tau2.agent.llm_agent.LLMAgent`` (or a subclass
of it): the evaluator builds one fresh agent per episode via :meth:`build_agent`
and plugs it into the orchestrator.

The underlying LLM (deepseek) is configured by the framework and passed in as
``llm`` / ``llm_args`` — the proposer does **not** edit how the model is wired,
only the *strategy* wrapped around it. Concretely a candidate may:

- override the agent's ``system_prompt`` to inject extra instructions/strategy
  on top of the (fixed) domain ``policy`` — e.g. planning, verification habits,
  tool-use discipline, when to ask the user vs. act
- subclass ``LLMAgent`` and override ``generate_next_message`` /
  ``_generate_next_message`` to add reflection, retry, tool-call validation, or
  self-consistency before returning the assistant message
- reshape the message history the model sees, or augment tool descriptions

It may **not** change the ``domain_policy`` text itself (that is part of the
task and is what the agent is being graded against), nor the user simulator, nor
the evaluation.

The seed scaffold (``PassthroughTau2Scaffold``) adds zero strategy: it returns a
plain ``LLMAgent`` — exactly tau2's base agent behavior, the starting point the
optimizer improves on.

``tau2`` is imported here (this module is part of the tau2 backend), so this
file may only be imported in a tau2-capable venv. The shared agentic core and
the dynamic loader stay tau2-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tau2.agent.llm_agent import LLMAgent

from worldcalib.optcore.scaffold_base import ScaffoldMixin

if TYPE_CHECKING:
    from tau2.environment.tool import Tool


class Tau2Scaffold(ScaffoldMixin):
    """Base class for an optimizable tau2 agent policy.

    Subclasses override :meth:`build_agent` to add strategy. The default
    implementation returns tau2's stock ``LLMAgent`` (pure pass-through). The
    ``name`` / ``config`` / ``fresh`` plumbing comes from
    :class:`ScaffoldMixin`.
    """

    name: str = "tau2_scaffold"

    # ── the optimizable surface ──────────────────────────────────────────────

    def build_agent(
        self,
        *,
        tools: list["Tool"],
        domain_policy: str,
        llm: str,
        llm_args: dict[str, Any],
    ) -> LLMAgent:
        """Build the tau2 agent for one episode.

        Override this to add strategy (return an ``LLMAgent`` subclass, or an
        ``LLMAgent`` with an augmented system prompt). The default is tau2's
        stock agent: the tools and domain policy are forwarded unchanged and the
        model decides each step on its own.

        Args:
            tools: The environment tools the agent may call (already includes the
                domain's agent tools).
            domain_policy: The domain policy text the agent must follow. Fixed by
                the task — do not alter it; layer strategy *around* it instead.
            llm: The litellm model id for the agent (e.g. ``deepseek/deepseek-chat``).
            llm_args: Extra kwargs forwarded to litellm (temperature, timeout, ...).
        """
        return LLMAgent(
            tools=tools,
            domain_policy=domain_policy,
            llm=llm,
            llm_args=dict(llm_args),
        )
