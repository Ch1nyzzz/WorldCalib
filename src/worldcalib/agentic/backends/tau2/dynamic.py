"""Dynamic loading for candidate tau2 agent scaffolds.

A thin tau2-specific shell over the generic
:func:`worldcalib.optcore.dynamic.load_candidate_selfdistill_scaffold`: it injects
the tau2 registry builder, the source-class map (name -> (module, class) inside
a workspace snapshot), the default seed key, and the tau2 type check, then lets
the shared loader handle the source-backed / built-in / dynamic-module control
flow.

Routed to from ``dynamic.load_candidate_scaffold`` when
``candidate["kind"] == "tau2_agent"``. Kept agentrl-free (tau2 runs in its own
eval venv without agentrl); ``tau2`` is pulled in only transitively via the
registry/base imports, which themselves live in the tau2 backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcalib.agentic.backends.tau2 import build_tau2_scaffold
from worldcalib.agentic.backends.tau2.base import Tau2Scaffold
from worldcalib.optcore.dynamic import load_candidate_selfdistill_scaffold

# Source-backed tau2 scaffolds: name -> (module, class) inside the snapshot.
# The proposer edits these in-place (same module path), so the mapping is fixed.
SOURCE_TAU2_SCAFFOLD_CLASSES: dict[str, tuple[str, str]] = {
    "tau2_passthrough": (
        "worldcalib.agentic.backends.tau2.seed_passthrough",
        "PassthroughTau2Scaffold",
    ),
}


def _is_tau2_scaffold_like(obj: Any) -> bool:
    if isinstance(obj, Tau2Scaffold):
        return True
    return hasattr(obj, "build_agent") and hasattr(obj, "name")


def load_candidate_tau2_scaffold(
    candidate: dict[str, Any], *, project_root: Path
) -> Tau2Scaffold:
    """Instantiate a tau2 scaffold from pending_eval candidate metadata."""
    return load_candidate_selfdistill_scaffold(
        candidate,
        project_root=project_root,
        registry_build=build_tau2_scaffold,
        source_classes=SOURCE_TAU2_SCAFFOLD_CLASSES,
        default_seed="tau2_passthrough",
        is_compatible=_is_tau2_scaffold_like,
    )
