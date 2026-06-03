"""Dynamic loading for candidate ARC-AGI-2 solver scaffolds.

The ARC analogue of the agentbench / tau2 candidate loaders: it produces an
``ArcScaffold`` from pending_eval candidate metadata. The control flow
(source-backed edited scaffold → built-in registry → dynamic
module/class/factory/build_scaffold/SCAFFOLD_CLASS) is identical across backends
and lives once in :func:`worldcalib.optcore.dynamic.load_candidate_selfdistill_scaffold`;
this module only parameterizes it with ARC's registry builder, source-class map,
default seed key, and type check.

Routed to from ``dynamic.load_candidate_scaffold`` when
``candidate["kind"] == "arc_solver"``. Kept agentrl-free (ARC runs as a
single-shot reasoning benchmark with no agent framework).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcalib.optcore.dynamic import load_candidate_selfdistill_scaffold
from worldcalib.reasoning.arc_scaffolds import build_arc_scaffold
from worldcalib.reasoning.arc_scaffolds.base import ArcScaffold

# Source-backed ARC scaffolds: name -> (module, class) inside the snapshot.
# The proposer edits these in-place (same module path), so the mapping is fixed.
SOURCE_ARC_SCAFFOLD_CLASSES: dict[str, tuple[str, str]] = {
    "arc_passthrough": (
        "worldcalib.reasoning.arc_scaffolds.seed_passthrough",
        "PassthroughArcScaffold",
    ),
}


def _is_arc_scaffold_like(obj: Any) -> bool:
    if isinstance(obj, ArcScaffold):
        return True
    return hasattr(obj, "solve_task") and hasattr(obj, "name")


def load_candidate_arc_scaffold(
    candidate: dict[str, Any], *, project_root: Path
) -> ArcScaffold:
    """Instantiate an ARC scaffold from pending_eval candidate metadata."""

    return load_candidate_selfdistill_scaffold(
        candidate,
        project_root=project_root,
        registry_build=build_arc_scaffold,
        source_classes=SOURCE_ARC_SCAFFOLD_CLASSES,
        default_seed="arc_passthrough",
        is_compatible=_is_arc_scaffold_like,
    )
