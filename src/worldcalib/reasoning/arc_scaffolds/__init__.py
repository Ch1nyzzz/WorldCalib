"""Registry of built-in ARC-AGI-2 solver scaffolds (the optimizable surface).

Kept agentrl-free and snapshot-safe on purpose: ARC runs as a single-shot
reasoning benchmark with no agent framework, and the proposer edits
``seed_passthrough.py`` inside a snapshot that copies only the ``arc_scaffolds``
tree plus the locomo base files. Importing this package therefore pulls in only
the standard library and ``worldcalib`` ``model`` / ``schemas`` / ``scaffolds.base``
(transitively, via ``base`` / ``seed_passthrough``).
"""

from __future__ import annotations

from worldcalib.reasoning.arc_scaffolds.base import ArcScaffold
from worldcalib.reasoning.arc_scaffolds.seed_passthrough import PassthroughArcScaffold

DEFAULT_ARC_SEED_SCAFFOLDS: tuple[str, ...] = ("arc_passthrough",)

_REGISTRY: dict[str, type[ArcScaffold]] = {
    "arc_passthrough": PassthroughArcScaffold,
}


def build_arc_scaffold(name: str) -> ArcScaffold:
    """Instantiate a built-in ARC scaffold by name."""
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown arc scaffold {name!r}; known: {sorted(_REGISTRY)}"
        ) from exc
    return cls()


__all__ = [
    "ArcScaffold",
    "PassthroughArcScaffold",
    "DEFAULT_ARC_SEED_SCAFFOLDS",
    "build_arc_scaffold",
]
