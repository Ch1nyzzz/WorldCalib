"""Toolathlon adapter — multi-app tool-use tasks recorded as QA-shaped results.

``ToolathlonSourceRunner`` emits per-task ``TaskResult`` rows with the QA fields
the shared trace builder expects (``task_id, question, gold_answer, prediction,
score, passed, prompt_tokens, completion_tokens, retrieved``) — here
``question`` is the task's primary app and ``prediction`` is the run status —
plus diagnostic ``app``/``run_status``/``eval_detail`` metadata, so we delegate
to ``_build_trace_for_qa`` like the GAIA / Spider2 adapters.
"""

from __future__ import annotations

from typing import Any

from ..schema import Trace
from .longmemeval import _build_trace_for_qa


class ToolathlonAdapter:
    name = "toolathlon"

    def build_trace(
        self,
        *,
        iteration: int,
        candidate_id: str,
        task: dict[str, Any],
    ) -> Trace:
        return _build_trace_for_qa(
            benchmark=self.name,
            iteration=iteration,
            candidate_id=candidate_id,
            task=task,
        )
