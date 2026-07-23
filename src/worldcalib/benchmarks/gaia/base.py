"""Base class for optimizable GAIA agent scaffolds.

A GAIA scaffold owns the full task-solving policy: given one task's prompt, it
runs a tool-using loop over the locked SUT model and returns a final answer.
``solve_task`` is the single editable seam the optimizer's proposer evolves
(see :mod:`worldcalib.benchmarks.gaia.seed_passthrough`).
"""

from __future__ import annotations

from typing import Any

from worldcalib.optcore.scaffold_base import ScaffoldMixin


class GaiaScaffold(ScaffoldMixin):
    """Common plumbing for GAIA agent scaffolds; subclasses implement ``solve_task``."""

    name: str = "gaia_scaffold"

    def solve_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Solve one GAIA task.

        ``task`` is a gold-free view: ``{"task_id", "level", "file_name",
        "prompt"}`` (never the final answer). Returns a dict with at least:

        - ``answer``: ``str`` — the extracted final answer (``""`` if none)
        - ``prompt_tokens`` / ``completion_tokens``: ``int`` — summed over turns
        - ``iterations``: ``int`` — turns used
        - ``finish_reason``: ``str | None``
        - ``error``: ``str | None`` — set when the loop raised
        """
        raise NotImplementedError
