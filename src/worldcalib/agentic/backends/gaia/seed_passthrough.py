"""GAIA seed scaffold — a tool-using FC loop over the locked SUT model.

Ported from robagent's ``agent/base.py`` capability layer: the LLM drives, the
loop dispatches its ``tool_calls``, and the result strings are fed back as
``tool`` messages until the model emits a turn with no tool_calls (the final
answer). Tools live in :mod:`gaia.tools` and are auto-registered via
``TOOL_SPECS``.

This is the **capability layer** — a real toolbox given upfront, no
stabilization. It is the single editable surface the optimizer's proposer
evolves: change ``SYSTEM_PROMPT``, the loop control, answer extraction, tool
handling, recovery on truncation/exhaustion, etc. — all in this one file.
"""

from __future__ import annotations

import re
from typing import Any

from worldcalib.agentic.backends.gaia.base import GaiaScaffold
from worldcalib.agentic.backends.gaia.llm import chat
from worldcalib.agentic.backends.gaia.tools import TOOL_SPECS, dispatch_tool

SYSTEM_PROMPT = (
    "You are an assistant solving a single benchmark task.\n\n"
    "Tools available: file_read (read an attached file by file_name), "
    "url_fetch (HTTP GET a URL and return its text), "
    "web_search (query a search engine), "
    "python_exec (run Python code, capturing stdout/stderr). "
    "Use them as needed to gather information and compute.\n\n"
    "When you have the final answer, end your response with one line:\n"
    "  FINAL ANSWER: <answer>\n\n"
    "The <answer> must be exactly the value the question asks for:\n"
    "- numbers: digits only, no thousand separators, no units unless asked\n"
    "- strings: no extra prefix or explanation\n"
    "- lists: comma-separated values, no brackets\n"
    "Do not write anything after the FINAL ANSWER line."
)

MAX_ITERATIONS = 15
# DeepSeek thinking mode emits a lot of reasoning_content; 8192 leaves headroom
# for thinking + content + tool_calls per turn.
PER_TURN_MAX_TOKENS = 8192

_FINAL_RE = re.compile(r"FINAL ANSWER:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _extract_final_answer(text: str) -> str:
    if not text:
        return ""
    matches = list(_FINAL_RE.finditer(text))
    if matches:
        return matches[-1].group(1).strip()
    return text.strip()


class PassthroughGaiaScaffold(GaiaScaffold):
    """The seed GAIA agent: an FC loop with the four tools, no stabilization."""

    name = "gaia_passthrough"

    def solve_task(self, task: dict[str, Any]) -> dict[str, Any]:
        prompt = task["prompt"]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        raw_content = ""
        finish_reason: str | None = None
        prompt_tokens = 0
        completion_tokens = 0
        iteration = 0

        for iteration in range(1, MAX_ITERATIONS + 1):
            try:
                result = chat(
                    messages=messages,
                    tools=TOOL_SPECS,
                    tool_choice="auto",
                    max_tokens=PER_TURN_MAX_TOKENS,
                )
            except Exception as e:  # noqa: BLE001 — surface as an episode error
                return {
                    "answer": _extract_final_answer(raw_content),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "iterations": iteration,
                    "finish_reason": finish_reason,
                    "error": f"{type(e).__name__}: {e}",
                }

            raw_content = result.get("content") or ""
            finish_reason = result.get("finish_reason")
            usage = result.get("usage") or {}
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)

            messages.append(result["assistant_message"])

            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                break

            for tc in tool_calls:
                tool_name = tc.get("name") or ""
                tool_args = tc.get("arguments") if tc.get("arguments") is not None else {}
                tool_call_id = tc.get("id") or f"call_{iteration}_{tool_name}"
                tool_result = dispatch_tool(
                    tool_name, tool_args if isinstance(tool_args, dict) else {}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result,
                    }
                )

        return {
            "answer": _extract_final_answer(raw_content),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "iterations": iteration,
            "finish_reason": finish_reason,
            "error": None,
        }


def build_scaffold() -> GaiaScaffold:
    return PassthroughGaiaScaffold()


SCAFFOLD_CLASS = PassthroughGaiaScaffold
