"""GAIA backend — a ported tool-using FC agent over the locked DeepSeek SUT.

Built-in scaffolds are looked up by name via :func:`build_gaia_scaffold`; the
seed (``gaia_passthrough``) is the editable capability layer the optimizer's
proposer evolves.
"""

from __future__ import annotations

from worldcalib.agentic.backends.gaia.base import GaiaScaffold
from worldcalib.agentic.backends.gaia.seed_passthrough import PassthroughGaiaScaffold

DEFAULT_GAIA_SEED_SCAFFOLDS: tuple[str, ...] = ("gaia_passthrough",)

_REGISTRY: dict[str, type[GaiaScaffold]] = {
    "gaia_passthrough": PassthroughGaiaScaffold,
}


def build_gaia_scaffold(name: str) -> GaiaScaffold:
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown gaia scaffold {name!r}; known: {sorted(_REGISTRY)}"
        ) from exc
    return cls()


__all__ = [
    "GaiaScaffold",
    "PassthroughGaiaScaffold",
    "DEFAULT_GAIA_SEED_SCAFFOLDS",
    "build_gaia_scaffold",
]
