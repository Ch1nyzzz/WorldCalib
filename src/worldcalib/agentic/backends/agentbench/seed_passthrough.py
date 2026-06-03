"""Seed agent scaffold — pure pass-through == the FC base agent.

This is the proposer's starting point. It adds no strategy: the conversation
``messages`` and ``tools`` are forwarded straight to the underlying deepseek
client (the inherited :meth:`AgentScaffold.query` default). The optimizer
evolves this into a smarter ``query`` strategy.
"""

from __future__ import annotations

from worldcalib.agentic.backends.agentbench.base import AgentScaffold


class PassthroughAgentScaffold(AgentScaffold):
    """The FC base agent as an optimizable scaffold: forwards everything as-is."""

    name = "agent_passthrough"
    # query() is inherited from AgentScaffold — a pure pass-through.


def build_scaffold() -> AgentScaffold:
    """Factory hook used by the dynamic candidate loader."""
    return PassthroughAgentScaffold()


SCAFFOLD_CLASS = PassthroughAgentScaffold
