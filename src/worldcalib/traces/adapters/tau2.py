"""tau2 adapter — agent episodes recorded as QA-shaped task results.

``Tau2EvaluationRunner`` emits per-episode ``TaskResult`` rows with the same
fields the QA trace builder expects (``task_id, question, gold_answer,
prediction, score, passed, prompt_tokens, completion_tokens, retrieved``), so we
delegate to the shared ``_build_trace_for_qa`` helper like the AgentBench
adapter.
"""

from __future__ import annotations

from typing import Any

from ..schema import Trace
from .longmemeval import _build_trace_for_qa


class Tau2Adapter:
    name = "tau2"

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
