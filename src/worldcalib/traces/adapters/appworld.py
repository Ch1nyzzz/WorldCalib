"""AppWorld adapter — interactive coding-agent tasks recorded as QA-shaped results.

``AppWorldSourceRunner`` emits per-task ``TaskResult`` rows with the QA fields the
shared trace builder expects (``task_id, question, gold_answer, prediction,
score, passed, prompt_tokens, completion_tokens, retrieved``) — here ``question``
is the AppWorld task id and ``prediction`` is success/fail — plus diagnostic
``steps``/``run_status`` metadata, so we delegate to ``_build_trace_for_qa`` like
the toolathlon / GAIA / Spider2 adapters.
"""

from __future__ import annotations

from typing import Any

from ..schema import Trace
from .longmemeval import _build_trace_for_qa


class AppWorldAdapter:
    name = "appworld"

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
