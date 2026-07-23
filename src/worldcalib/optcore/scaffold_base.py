"""Shared state-free scaffold mixin for agent-policy benchmarks."""

from __future__ import annotations

from typing import Optional

from worldcalib.scaffolds.base import ScaffoldConfig


class ScaffoldMixin:
    """Common name/config/fresh plumbing for optimizable agent scaffolds.

    Subclasses provide the benchmark-specific optimization surface; this mixin
    owns only identity, configuration, and lifecycle.
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
