"""Dynamic loading for candidate GAIA agent scaffolds.

A thin GAIA-specific shell over the generic
:func:`worldcalib.optcore.dynamic.load_candidate_selfdistill_scaffold`: it
injects the GAIA registry builder, the source-class map (name -> (module, class)
inside a workspace snapshot), the default seed key, and the GAIA type check.

Routed to from ``dynamic.load_candidate_scaffold`` when
``candidate["kind"] == "gaia_agent"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcalib.benchmarks.gaia import build_gaia_scaffold
from worldcalib.benchmarks.gaia.base import GaiaScaffold
from worldcalib.optcore.dynamic import load_candidate_selfdistill_scaffold

# Source-backed GAIA scaffolds: name -> (module, class) inside the snapshot.
# The proposer edits these in-place (same module path), so the mapping is fixed.
SOURCE_GAIA_SCAFFOLD_CLASSES: dict[str, tuple[str, str]] = {
    "gaia_passthrough": (
        "worldcalib.benchmarks.gaia.seed_passthrough",
        "PassthroughGaiaScaffold",
    ),
}


def _is_gaia_scaffold_like(obj: Any) -> bool:
    if isinstance(obj, GaiaScaffold):
        return True
    return hasattr(obj, "solve_task") and hasattr(obj, "name")


def load_candidate_gaia_scaffold(
    candidate: dict[str, Any], *, project_root: Path
) -> GaiaScaffold:
    """Instantiate a GAIA scaffold from pending_eval candidate metadata."""
    return load_candidate_selfdistill_scaffold(
        candidate,
        project_root=project_root,
        registry_build=build_gaia_scaffold,
        source_classes=SOURCE_GAIA_SCAFFOLD_CLASSES,
        default_seed="gaia_passthrough",
        is_compatible=_is_gaia_scaffold_like,
    )
