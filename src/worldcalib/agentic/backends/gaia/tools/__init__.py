"""Tool registry for the GAIA FC agent (ported from robagent).

``TOOL_SPECS`` is the OpenAI function-call shape list passed to
``gaia.llm.chat(tools=...)``. ``dispatch_tool(name, args)`` runs a tool and
returns a string result for the ``tool`` message (it never raises).

Adding a tool: write ``gaia/tools/<name>.py`` exposing ``SPEC: dict`` (OpenAI
function-call shape) and ``run(args: dict) -> str``; add it to ``_TOOLS`` below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load the repo .env eagerly so smoke tests see TAVILY_API_KEY/SERPER_API_KEY etc.
_REPO_ROOT = Path(__file__).resolve().parents[6]
load_dotenv(dotenv_path=_REPO_ROOT / ".env")

from . import file_read, python_exec, url_fetch, web_search  # noqa: E402

_TOOLS = {
    "file_read": file_read,
    "url_fetch": url_fetch,
    "web_search": web_search,
    "python_exec": python_exec,
}

TOOL_SPECS: list[dict[str, Any]] = [t.SPEC for t in _TOOLS.values()]
TOOL_NAMES: tuple[str, ...] = tuple(_TOOLS.keys())


def dispatch_tool(name: str, args: dict | None) -> str:
    """Run the named tool with an args dict; return string output (never raises)."""
    if name not in _TOOLS:
        return f"ERROR: unknown tool {name!r}. Available: {list(_TOOLS)}"
    try:
        return _TOOLS[name].run(args or {})
    except Exception as e:  # noqa: BLE001 — a tool error must not kill the loop
        return f"ERROR running {name}: {type(e).__name__}: {e}"
