"""Toolathlon backend: a containerized multi-app tool-use benchmark.

Unlike the in-process scaffolds, Toolathlon is evaluated through its own
``run_parallel.py`` containerized scheduler (see runner.py). The proposer evolves
the agent-policy source (the shared agent_system_prompt + the TaskAgent loop +
the history/tool context managers); candidates are graded by Toolathlon's
end-state evaluator.
"""

from __future__ import annotations

from worldcalib.benchmarks.toolathlon.runner import (
    DEFAULT_TOOLATHLON_AGENT_NAME,
)

DEFAULT_TOOLATHLON_SEED_SCAFFOLDS: tuple[str, ...] = (DEFAULT_TOOLATHLON_AGENT_NAME,)

__all__ = [
    "DEFAULT_TOOLATHLON_AGENT_NAME",
    "DEFAULT_TOOLATHLON_SEED_SCAFFOLDS",
]
