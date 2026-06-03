"""Dynamic loading for candidate agent scaffolds (agentrl ``BaseClient`` subclasses).

Thin AgentBench shell over the generic
:func:`worldcalib.optcore.dynamic.load_candidate_selfdistill_scaffold`: it injects
the AgentBench registry builder, the source-class map (scaffold_name ->
(module, class) inside a workspace snapshot), the default seed key, and the
AgentBench compatibility check, then defers the entire control flow to the
shared loader.

Routed to from ``dynamic.load_candidate_scaffold`` when ``candidate["kind"] ==
"agent"``. This module stays import-light at top level — the ``AgentScaffold``
type imported for the ``isinstance`` check pulls in ``agentrl``, which is
expected for the agentbench backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcalib.agentic.backends.agentbench import build_agent_scaffold
from worldcalib.agentic.backends.agentbench.base import AgentScaffold
from worldcalib.optcore.dynamic import load_candidate_selfdistill_scaffold

# Source-backed agent scaffolds: name -> (module, class) inside the snapshot.
# The proposer edits these in-place (same module path), so the mapping is fixed.
SOURCE_AGENT_SCAFFOLD_CLASSES: dict[str, tuple[str, str]] = {
    "agent_passthrough": (
        "worldcalib.agentic.backends.agentbench.seed_passthrough",
        "PassthroughAgentScaffold",
    ),
}


def _is_agent_like(obj: Any) -> bool:
    if isinstance(obj, AgentScaffold):
        return True
    return hasattr(obj, "query") and hasattr(obj, "name")


def load_candidate_agent_scaffold(
    candidate: dict[str, Any], *, project_root: Path
) -> AgentScaffold:
    """Instantiate an agent scaffold from pending_eval candidate metadata."""
    return load_candidate_selfdistill_scaffold(
        candidate,
        project_root=project_root,
        registry_build=build_agent_scaffold,
        source_classes=SOURCE_AGENT_SCAFFOLD_CLASSES,
        default_seed="agent_passthrough",
        is_compatible=_is_agent_like,
    )
