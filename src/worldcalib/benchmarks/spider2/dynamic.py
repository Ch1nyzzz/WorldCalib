"""Dynamic loading for candidate Spider2 agent scaffolds.

A thin Spider2-specific shell over the generic
:func:`worldcalib.optcore.dynamic.load_candidate_selfdistill_scaffold`: it injects
the Spider2 registry builder, the source-class map (name -> (module, class) inside
a workspace snapshot), the default seed key, and the Spider2 type check.

Routed to from ``dynamic.load_candidate_scaffold`` when
``candidate["kind"] == "spider2_agent"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcalib.benchmarks.spider2 import build_spider2_scaffold
from worldcalib.benchmarks.spider2.base import Spider2Scaffold
from worldcalib.optcore.dynamic import load_candidate_selfdistill_scaffold

# Source-backed Spider2 scaffolds: name -> (module, class) inside the snapshot.
SOURCE_SPIDER2_SCAFFOLD_CLASSES: dict[str, tuple[str, str]] = {
    "spider2_passthrough": (
        "worldcalib.benchmarks.spider2.seed_passthrough",
        "PassthroughSpider2Scaffold",
    ),
}


def _is_spider2_scaffold_like(obj: Any) -> bool:
    if isinstance(obj, Spider2Scaffold):
        return True
    return hasattr(obj, "solve_task") and hasattr(obj, "name")


def load_candidate_spider2_scaffold(
    candidate: dict[str, Any], *, project_root: Path
) -> Spider2Scaffold:
    """Instantiate a Spider2 scaffold from pending_eval candidate metadata."""
    return load_candidate_selfdistill_scaffold(
        candidate,
        project_root=project_root,
        registry_build=build_spider2_scaffold,
        source_classes=SOURCE_SPIDER2_SCAFFOLD_CLASSES,
        default_seed="spider2_passthrough",
        is_compatible=_is_spider2_scaffold_like,
    )
