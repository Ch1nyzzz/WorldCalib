"""Shared self-distill scaffold mixin.

``ScaffoldMixin`` collects the backend-agnostic plumbing every agent scaffold
needs — the ``name`` / ``reference_urls`` class attributes, the ``__init__``
that stores a :class:`ScaffoldConfig`, and the ``fresh()`` factory the
evaluators call to get a state-free instance per episode.

Both backend bases mix this in:

- ``AgentScaffold(BaseClient, ScaffoldMixin)`` (agentbench / agentrl)
- ``Tau2Scaffold(ScaffoldMixin)`` (tau2)

This module is import-light and stays free of ``agentrl`` / ``tau2`` so it can
sit in candidate snapshots and import in any venv.
"""

from __future__ import annotations

from typing import Optional

from worldcalib.scaffolds.base import ScaffoldConfig


class ScaffoldMixin:
    """Common name/config/fresh plumbing for optimizable agent scaffolds.

    Subclasses override the backend-specific optimizable surface (``query`` for
    agentbench, ``build_agent`` for tau2). This mixin only owns identity and
    lifecycle, none of which touches ``agentrl`` or ``tau2``.
    """

    name: str = "agentic_scaffold"
    reference_urls: tuple[str, ...] = ()

    def __init__(self, config: Optional[ScaffoldConfig] = None) -> None:
        self.config = config or ScaffoldConfig()

    def fresh(self) -> "ScaffoldMixin":
        """Return a new, state-free instance of the same scaffold class.

        The evaluator builds one fresh scaffold per episode so any cross-turn
        state held on ``self`` never leaks between episodes.
        """
        return type(self)(self.config)
