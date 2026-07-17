"""Spider2 seed scaffold — single-shot text-to-SQL over the locked SUT model.

This reproduces the deepseek-v4-flash Spider2-lite baseline (~0.50 on the local
sqlite subset): feed the model the DB schema + external knowledge + question, ask
for ONE SQLite query in a ```sql block, extract it. No verification, no repair.

This is the **capability layer** — the single editable surface the optimizer's
proposer evolves: sharpen ``build_prompt`` (schema representation, few-shot
discipline, dialect hints), add a self-verification / EXPLAIN pass, re-ask on
empty or syntactically invalid SQL, sample rows from ``db_path`` for grounding,
decompose hard questions, etc. — all inside this one file. The grading side
(scorer/evaluation/data) is intentionally NOT in the editable workspace.
"""

from __future__ import annotations

import re
from typing import Any

from worldcalib.agentic.backends.spider2.base import Spider2Scaffold
from worldcalib.agentic.backends.spider2.llm import chat

MAX_TOKENS = 8000  # v4-flash is a reasoning model; leave room for thinking + SQL

_SQL_BLOCK_RE = re.compile(r"```sql\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_BLOCK_RE = re.compile(r"```\s*(.*?)```", re.DOTALL)


def extract_sql(text: str) -> str:
    """Pull the SQL out of a model response (```sql block preferred)."""
    if not text:
        return ""
    m = _SQL_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _ANY_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def build_prompt(task: dict[str, Any]) -> str:
    """Build the single user-turn prompt from the gold-free task view.

    Matches the deepseek-v4-flash Spider2-lite baseline verbatim (one user turn,
    instruction folded in) so the seed reproduces the calibrated baseline
    pass-rate; the proposer is free to restructure this (system prompt, few-shot,
    etc.) as an improvement.
    """
    schema = task.get("schema") or ""
    ek = task.get("external_knowledge") or ""
    return (
        "You are an expert SQLite analyst. Given the database schema and a question, "
        "write ONE SQLite query that answers it. Return only the SQL in a ```sql block.\n\n"
        f"# Schema\n{schema}\n\n"
        f"# External knowledge\n{ek}\n\n"
        f"# Question\n{task['question']}\n"
    )


class PassthroughSpider2Scaffold(Spider2Scaffold):
    """The seed Spider2 agent: one generation, extract one SQL query."""

    name = "spider2_passthrough"

    def solve_task(self, task: dict[str, Any]) -> dict[str, Any]:
        messages = [
            {"role": "user", "content": build_prompt(task)},
        ]
        try:
            result = chat(messages=messages, max_tokens=MAX_TOKENS)
        except Exception as e:  # noqa: BLE001 — surface as an episode error
            return {
                "sql": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "error": f"{type(e).__name__}: {e}",
            }

        usage = result.get("usage") or {}
        return {
            "sql": extract_sql(result.get("content") or ""),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "error": None,
        }


def build_scaffold() -> Spider2Scaffold:
    return PassthroughSpider2Scaffold()


SCAFFOLD_CLASS = PassthroughSpider2Scaffold
