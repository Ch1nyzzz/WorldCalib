"""Registry of built-in tau2 agent scaffolds (the optimizable agent policies).

Kept agentrl-free on purpose: tau2 runs in its own eval venv
(``.venv-tau2-eval`` = worldcalib + tau2, no agentrl), so importing this package
must not pull the AgentBench backend (which imports agentrl). Only ``tau2`` is
imported here, transitively via ``base`` / ``seed_passthrough``.
"""

from __future__ import annotations

from worldcalib.agentic.backends.tau2.base import Tau2Scaffold
from worldcalib.agentic.backends.tau2.seed_passthrough import PassthroughTau2Scaffold

DEFAULT_TAU2_SEED_SCAFFOLDS: tuple[str, ...] = ("tau2_passthrough",)

_REGISTRY: dict[str, type[Tau2Scaffold]] = {
    "tau2_passthrough": PassthroughTau2Scaffold,
}


def build_tau2_scaffold(name: str) -> Tau2Scaffold:
    """Instantiate a built-in tau2 scaffold by name."""
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown tau2 scaffold {name!r}; known: {sorted(_REGISTRY)}"
        ) from exc
    return cls()


__all__ = [
    "Tau2Scaffold",
    "PassthroughTau2Scaffold",
    "DEFAULT_TAU2_SEED_SCAFFOLDS",
    "build_tau2_scaffold",
]
