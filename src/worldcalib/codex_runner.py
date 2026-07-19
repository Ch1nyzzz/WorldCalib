"""Codex CLI proposer runner.

Runs ``codex exec`` non-interactively as the proposer, mirroring
:func:`worldcalib.claude_runner.run_claude_prompt`'s contract: same
:class:`~worldcalib.claude_runner.ClaudeResult` shape, same log files, so
the optimizer's downstream handling (metrics, tool-access telemetry,
retry logic) is agent-agnostic.

Differences from the Claude path, all deliberate:

- **Auth.** Codex authenticates from ``$CODEX_HOME/auth.json`` (ChatGPT
  OAuth), never from env tokens. ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL``
  are STRIPPED from the subprocess env: the repo ``.env`` exports a solver
  key under those names, and codex would silently prefer it over the
  auth.json login — authenticating the proposer against the wrong account.
- **Contract delivery.** Codex has no ``--append-system-prompt``; the
  optimizer writes the benchmark skill to ``<workspace>/AGENTS.md``
  (``_deploy_codex_agents_md``) which codex auto-loads from the session cwd.
- **Sandbox.** The proposer runs on the host under codex's own
  ``workspace-write`` sandbox (writes confined to the workspace + /tmp,
  network off for model-generated commands). The Claude-path docker sandbox
  is not used: the codex CLI does not exist in those images.
- **MCP.** Codex has no per-workspace MCP config file; servers are injected
  per invocation via ``-c mcp_servers.<name>.*`` overrides (TOML values).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from worldcalib.claude_runner import (
    ClaudeResult,
    ProposerSandboxConfig,
    _add_shell_command_access,
    _add_written_lines,
    _count_text_lines,
    _agent_visible_cwd,
    _coerce,
    _dedupe_dicts,
    _empty_tool_access,
    _extract_session_metrics,
    _is_shell_tool_name,
    _jsonl_events,
    _make_relative,
    _merge_usage_dicts,
    _prepare_agent_command,
    _tool_path,
    _uses_docker_sandbox,
    _write_logs,
)
from collections import Counter

CODEX_EXECUTABLE = "codex"
DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_CODEX_REASONING_EFFORT = "xhigh"
# Env names codex must never inherit: the repo .env exports the SOLVER's
# OpenAI-compatible credentials under these names, and codex prefers an env
# key over its auth.json login when one is present.
_STRIPPED_ENV_VARS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORGANIZATION")


def has_codex_cli() -> bool:
    return shutil.which(CODEX_EXECUTABLE) is not None


def _codex_env(codex_home: str | None) -> dict[str, str]:
    env = dict(os.environ)
    for name in _STRIPPED_ENV_VARS:
        env.pop(name, None)
    if codex_home:
        env["CODEX_HOME"] = str(Path(codex_home).expanduser())
    return env


def _toml_value(value: Any) -> str:
    """Render a python value as a TOML literal for a ``-c key=value`` override.

    Codex parses the part after ``=`` as TOML, not JSON: strings must be
    quoted, dicts are inline tables (``{k = "v"}``), lists are arrays.
    """

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        inner = ", ".join(f"{key} = {_toml_value(val)}" for key, val in value.items())
        return "{" + inner + "}"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _mcp_override_args(
    mcp_servers: Mapping[str, Mapping[str, Any]] | None,
) -> list[str]:
    """``-c mcp_servers.<name>.command/args/env=...`` overrides for codex."""

    if not mcp_servers:
        return []
    out: list[str] = []
    for name, spec in mcp_servers.items():
        for key in ("command", "args", "env"):
            value = spec.get(key)
            if value is None:
                continue
            out += ["-c", f"mcp_servers.{name}.{key}={_toml_value(value)}"]
    return out


def run_codex_prompt(
    prompt: str,
    *,
    cwd: Path,
    log_dir: Path,
    name: str,
    model: str = DEFAULT_CODEX_MODEL,
    reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT,
    timeout_s: int = 2400,
    sandbox: ProposerSandboxConfig | None = None,
    codex_home: str | None = None,
    mcp_servers: Mapping[str, Mapping[str, Any]] | None = None,
) -> ClaudeResult:
    """Run ``codex exec`` non-interactively and persist logs."""

    cwd = cwd.resolve(strict=False)
    agent_cwd = _agent_visible_cwd(cwd, sandbox=sandbox)
    command = (
        CODEX_EXECUTABLE,
        "exec",
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={_toml_value(reasoning_effort)}",
        *_mcp_override_args(mcp_servers),
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--cd",
        str(agent_cwd),
        "--ephemeral",
        "--json",
        "-",
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    env = _codex_env(codex_home)
    prepared = _prepare_agent_command(command, cwd=cwd, sandbox=sandbox, env=env)

    if prepared.error:
        result = ClaudeResult(
            returncode=None,
            timed_out=False,
            stdout="",
            stderr=prepared.error,
            raw_stdout="",
            command=prepared.command,
            usage=None,
            tool_access=_empty_tool_access(),
            duration_s=0.0,
            metrics={},
        )
        _write_logs(result, log_dir=log_dir, name=name, prompt=prompt)
        return result

    if not _uses_docker_sandbox(sandbox) and not has_codex_cli():
        result = ClaudeResult(
            returncode=None,
            timed_out=False,
            stdout="",
            stderr="codex CLI not found on PATH",
            raw_stdout="",
            command=command,
            usage=None,
            tool_access=_empty_tool_access(),
            duration_s=0.0,
            metrics={},
        )
        _write_logs(result, log_dir=log_dir, name=name, prompt=prompt)
        return result

    try:
        completed = subprocess.run(
            prepared.command,
            input=prompt,
            cwd=str(prepared.run_cwd),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            env=env,
        )
        raw_stdout = completed.stdout or ""
        stdout, usage = _extract_codex_result(raw_stdout)
        tool_access = _extract_codex_tool_access(raw_stdout, cwd=prepared.extract_cwd)
        duration_s = time.time() - started
        result = ClaudeResult(
            returncode=completed.returncode,
            timed_out=False,
            stdout=stdout,
            stderr=completed.stderr or "",
            raw_stdout=raw_stdout,
            command=prepared.command,
            usage=usage,
            tool_access=tool_access,
            duration_s=duration_s,
            metrics=_extract_session_metrics(
                usage=usage,
                tool_access=tool_access,
                duration_s=duration_s,
            ),
        )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = _coerce(exc.stdout)
        tool_access = _extract_codex_tool_access(raw_stdout, cwd=prepared.extract_cwd)
        duration_s = time.time() - started
        result = ClaudeResult(
            returncode=None,
            timed_out=True,
            stdout=raw_stdout,
            stderr=_coerce(exc.stderr),
            raw_stdout=raw_stdout,
            command=prepared.command,
            usage=None,
            tool_access=tool_access,
            duration_s=duration_s,
            metrics=_extract_session_metrics(
                usage=None,
                tool_access=tool_access,
                duration_s=duration_s,
            ),
        )

    _write_logs(result, log_dir=log_dir, name=name, prompt=prompt)
    return result


# ---------------------------------------------------------------------------
# ``codex exec --json`` event-stream parsing.
# ---------------------------------------------------------------------------
def _extract_codex_result(raw_stdout: str) -> tuple[str, dict[str, Any] | None]:
    """Final assistant text + merged usage from the ``--json`` event stream."""

    text_chunks: list[str] = []
    usage: dict[str, Any] = {}
    for event in _jsonl_events(raw_stdout):
        event_type = str(event.get("type") or event.get("event") or "")
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            value = item.get("text")
            if isinstance(value, str) and value:
                text_chunks.append(value)
        if event_type in {"result", "final", "agent_message", "message"}:
            for key in ("result", "message", "text", "content", "last_message"):
                value = event.get(key)
                if isinstance(value, str) and value:
                    text_chunks.append(value)
                    break
        event_usage = event.get("usage")
        if isinstance(event_usage, dict):
            usage["usage"] = _merge_usage_dicts(
                usage.get("usage") if isinstance(usage.get("usage"), dict) else {},
                event_usage,
            )
        for key in (
            "total_cost_usd",
            "duration_ms",
            "duration_api_ms",
            "num_turns",
            "session_id",
        ):
            if key in event:
                usage[key] = event[key]
    return "\n".join(text_chunks) or raw_stdout, usage or None


def _codex_tool_name(event: dict[str, Any]) -> str:
    item = event.get("item")
    if isinstance(item, dict) and item.get("type") == "command_execution":
        return "Shell"
    for key in ("tool_name", "name", "tool", "command"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    if isinstance(item, dict):
        for key in ("tool_name", "name", "tool", "command"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _codex_tool_input(event: dict[str, Any]) -> dict[str, Any]:
    for key in ("input", "arguments", "args"):
        value = event.get(key)
        if isinstance(value, dict):
            return value
    item = event.get("item")
    if isinstance(item, dict):
        if item.get("type") == "command_execution" and isinstance(
            item.get("command"), str
        ):
            return {"command": item["command"]}
        for key in ("input", "arguments", "args"):
            value = item.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _codex_tool_output(event: dict[str, Any]) -> str:
    item = event.get("item")
    if isinstance(item, dict):
        for key in ("aggregated_output", "output", "stdout"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("aggregated_output", "output", "stdout"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_codex_tool_access(
    raw_stdout: str, *, cwd: Path | str | None = None
) -> dict[str, Any]:
    tool_uses: list[dict[str, Any]] = []
    files_read: dict[str, dict[str, int]] = {}
    files_written: dict[str, dict[str, int]] = {}
    grep_requests: list[dict[str, Any]] = []

    for event in _jsonl_events(raw_stdout):
        item = event.get("item")
        # command_execution items appear once as item.started and once as
        # item.completed; count only the completed one (it carries the output).
        if (
            isinstance(item, dict)
            and item.get("type") == "command_execution"
            and event.get("type") != "item.completed"
        ):
            continue
        name = _codex_tool_name(event)
        if not name:
            continue
        tool_input = _codex_tool_input(event)
        record = {
            "id": event.get("id") or event.get("call_id") or event.get("item_id"),
            "name": name,
            "input": tool_input,
        }
        output = _codex_tool_output(event)
        if output:
            record["_output"] = output
        tool_uses.append(record)
        path = _tool_path(tool_input)
        if path and name in {"Read", "read_file"}:
            rel = _make_relative(path, cwd)
            current = files_read.setdefault(rel, {"reads": 0, "lines": 0})
            current["reads"] += 1
        elif path and name in {"Write", "Edit", "apply_patch", "write_file"}:
            _add_written_lines(
                files_written,
                _make_relative(path, cwd),
                _count_text_lines(
                    tool_input.get("content") or tool_input.get("new_string")
                ),
            )
        elif name in {"Grep", "rg", "search"}:
            grep_requests.append(
                {
                    "pattern": tool_input.get("pattern") or tool_input.get("query"),
                    "path": tool_input.get("path"),
                    "glob": tool_input.get("glob"),
                }
            )
        elif _is_shell_tool_name(name):
            _add_shell_command_access(
                record,
                files_read=files_read,
                files_written=files_written,
                grep_requests=grep_requests,
                cwd=cwd,
            )

    for record in tool_uses:
        record.pop("_output", None)

    return {
        "read_files": sorted(files_read),
        "grep_requests": _dedupe_dicts(grep_requests),
        "tool_uses": tool_uses,
        "tool_counts": dict(
            sorted(Counter(str(item.get("name") or "") for item in tool_uses).items())
        ),
        "files_read": dict(sorted(files_read.items())),
        "files_written": dict(sorted(files_written.items())),
    }
