"""Base class for optimizable Spider2 text-to-SQL scaffolds.

A Spider2 scaffold owns the full single-shot text-to-SQL policy: given one
task's gold-free view (question + DB schema + external knowledge + an absolute
sqlite ``db_path``), it produces ONE SQL query string. ``solve_task`` is the
single editable seam the optimizer's proposer evolves (see
:mod:`worldcalib.benchmarks.spider2.seed_passthrough`).

Unlike the GAIA FC loop this is a single generation (optionally with the
scaffold's own self-repair / verification passes the proposer may add), but the
contract mirrors GAIA's so the shared self-distill optimizer loop is unchanged.
"""

from __future__ import annotations

from typing import Any

from worldcalib.optcore.scaffold_base import ScaffoldMixin


class Spider2Scaffold(ScaffoldMixin):
    """Common plumbing for Spider2 scaffolds; subclasses implement ``solve_task``."""

    name: str = "spider2_scaffold"

    def solve_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Solve one Spider2-lite task.

        ``task`` is a gold-free view built host-side by the evaluation runner:

        - ``instance_id``: ``str``
        - ``db``: ``str`` — database/schema name
        - ``question``: ``str`` — the natural-language question
        - ``external_knowledge``: ``str`` — domain doc text (may be empty)
        - ``schema``: ``str`` — the database DDL (``CREATE TABLE`` statements)
        - ``db_path``: ``str`` — absolute path to the sqlite file (read-only;
          the scaffold MAY query it for sample rows / richer schema, but must
          never use it to look up the gold answer)

        Returns a dict with at least:

        - ``sql``: ``str`` — the single SQL query to grade (``""`` if none)
        - ``prompt_tokens`` / ``completion_tokens``: ``int`` — summed over calls
        - ``error``: ``str | None`` — set when generation raised
        """
        raise NotImplementedError
