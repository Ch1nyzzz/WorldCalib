"""Agentic optimization backends.

Each backend (``agentbench``, ``tau2``) wires the shared agentic core to a
concrete benchmark. Backend-specific third-party imports (``agentrl`` for
agentbench, ``tau2`` for tau2) live **inside** their respective backend
packages only — never in this package init, which stays snapshot-safe.
"""

from __future__ import annotations

__all__: list[str] = []
