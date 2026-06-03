"""Registry of built-in agent scaffolds (the optimizable FC agent policies)."""

from __future__ import annotations

from worldcalib.agentic.backends.agentbench.base import AgentScaffold
from worldcalib.agentic.backends.agentbench.seed_passthrough import (
    PassthroughAgentScaffold,
)

DEFAULT_AGENT_SEED_SCAFFOLDS: tuple[str, ...] = ("agent_passthrough",)

_REGISTRY: dict[str, type[AgentScaffold]] = {
    "agent_passthrough": PassthroughAgentScaffold,
}


def build_agent_scaffold(name: str) -> AgentScaffold:
    """Instantiate a built-in agent scaffold by name."""
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown agent scaffold {name!r}; known: {sorted(_REGISTRY)}"
        ) from exc
    return cls()


__all__ = [
    "AgentScaffold",
    "PassthroughAgentScaffold",
    "DEFAULT_AGENT_SEED_SCAFFOLDS",
    "build_agent_scaffold",
]
