"""Seed tau2 scaffold — pure pass-through == tau2's base ``LLMAgent``.

This is the proposer's starting point. It adds no strategy: :meth:`build_agent`
returns tau2's stock ``LLMAgent`` with the environment tools and domain policy
forwarded unchanged (the inherited :meth:`Tau2Scaffold.build_agent` default).
The optimizer evolves this into a smarter agent — e.g. by returning an
``LLMAgent`` subclass that augments ``system_prompt`` or overrides
``generate_next_message`` to add planning / reflection / tool-call validation.

This file is the proposer's editable seed surface: it is snapshot-copied and
rewritten by the proposer, kept separate from ``base.py`` so the base plumbing
stays stable.

A worked example of the kind of override a candidate might write::

    from tau2.agent.llm_agent import LLMAgent, SYSTEM_PROMPT, AGENT_INSTRUCTION

    EXTRA_STRATEGY = "Before any irreversible tool call, confirm the user's intent."

    class StrategyAgent(LLMAgent):
        @property
        def system_prompt(self) -> str:
            base = SYSTEM_PROMPT.format(
                domain_policy=self.domain_policy,
                agent_instruction=AGENT_INSTRUCTION,
            )
            return base + "\n<strategy>\n" + EXTRA_STRATEGY + "\n</strategy>"

    class StrategyScaffold(Tau2Scaffold):
        name = "tau2_strategy"
        def build_agent(self, *, tools, domain_policy, llm, llm_args):
            return StrategyAgent(tools=tools, domain_policy=domain_policy,
                                 llm=llm, llm_args=dict(llm_args))
"""

from __future__ import annotations

from worldcalib.agentic.backends.tau2.base import Tau2Scaffold


class PassthroughTau2Scaffold(Tau2Scaffold):
    """tau2's base agent as an optimizable scaffold: forwards everything as-is."""

    name = "tau2_passthrough"
    # build_agent() is inherited from Tau2Scaffold — a pure pass-through.


def build_scaffold() -> Tau2Scaffold:
    """Factory hook used by the dynamic candidate loader."""
    return PassthroughTau2Scaffold()


SCAFFOLD_CLASS = PassthroughTau2Scaffold
