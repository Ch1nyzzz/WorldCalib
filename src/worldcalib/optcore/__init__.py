"""Neutral self-distill optimization core for WorldCalib.

This package holds the backend-agnostic contracts the agent backends
(AgentBench / agentrl and tau2) import: the scaffold mixin, the generic
candidate loader, the shared evaluation helpers, and the shared self-distill
optimizer skeleton.

Intentionally **import-light**: this file is copied verbatim into candidate
workspace snapshots and must import cleanly in any venv (including the
agentrl-free tau2 eval venv). It therefore performs **no** heavy imports — in
particular it must not pull in ``agentrl`` or ``tau2`` at module top level.
"""

from __future__ import annotations

__all__: list[str] = []
