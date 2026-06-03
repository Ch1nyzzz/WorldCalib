"""Agent-policy backends for WorldCalib (AgentBench / agentrl and tau2).

The backend-agnostic self-distill contracts the two agent backends share — the
scaffold mixin, the generic candidate loader, the shared evaluation helpers, and
the shared optimizer skeleton — now live in :mod:`worldcalib.optcore`. This
package holds only the concrete backends under ``backends/``.

Intentionally **import-light**: this file is copied verbatim into candidate
workspace snapshots and must import cleanly in any venv (including the
agentrl-free tau2 eval venv). It therefore performs **no** heavy imports — in
particular it must not pull in ``agentrl`` or ``tau2`` at module top level.
"""

from __future__ import annotations

__all__: list[str] = []
