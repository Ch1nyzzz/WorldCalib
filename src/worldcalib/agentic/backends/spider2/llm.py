"""DeepSeek chat client for the Spider2 text-to-SQL agent.

Same wiring as the GAIA backend: endpoint and model name come from env
(``MODEL_NAME``, ``DEEPSEEK_BASE_URL``, ``DEEPSEEK_API_KEY``) and the SUT model
is LOCKED so an evolved scaffold cannot silently vary it mid-experiment. Spider2
generation is single-shot (no tools), but ``chat()`` keeps the same signature as
GAIA's so the proposer can reuse familiar patterns and add tool calls / repair
loops if it wants.

Handles DeepSeek thinking-mode ``reasoning_content`` round-tripping, a soft
QPM/TPM limiter, and bounded retries with a shared 429 cooldown.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# Repo root is six levels up: spider2 → backends → agentic → worldcalib → src → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[5]
load_dotenv(dotenv_path=_REPO_ROOT / ".env")

DEFAULT_MODEL = os.environ.get("MODEL_NAME", "deepseek-v4-flash")
_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

if not _API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY not set in environment or .env")

_client = OpenAI(api_key=_API_KEY, base_url=_BASE_URL)

_RATE_LIMIT_PER_MIN = int(os.environ.get("LLM_RATE_LIMIT_PER_MIN", "5000"))
_TOKEN_LIMIT_PER_MIN = int(os.environ.get("LLM_TOKEN_LIMIT_PER_MIN", "50000000"))
_MAX_WALL_SECONDS = float(os.environ.get("LLM_MAX_WALL_SECONDS", "480"))
_PER_CALL_TIMEOUT = float(os.environ.get("LLM_PER_CALL_TIMEOUT", "150"))
_MAX_API_ATTEMPTS = int(os.environ.get("LLM_MAX_API_ATTEMPTS", "10"))
_DEFAULT_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8000"))

_cooldown_until: float = 0.0


def _set_cooldown(seconds: float) -> None:
    global _cooldown_until
    until = time.monotonic() + max(0.5, seconds)
    if until > _cooldown_until:
        _cooldown_until = until


def _wait_for_cooldown(deadline: float) -> None:
    while True:
        remaining = _cooldown_until - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5.0))


_rate_lock = threading.Lock()
_rate_window: "deque[float]" = deque()
_token_window: "deque[tuple[float, int]]" = deque()


def _prune_windows(now: float) -> None:
    while _rate_window and now - _rate_window[0] > 60.0:
        _rate_window.popleft()
    while _token_window and now - _token_window[0][0] > 60.0:
        _token_window.popleft()


def _tokens_in_window() -> int:
    return sum(n for _, n in _token_window)


def _acquire_rate_slot(token_estimate: int, *, deadline: float) -> None:
    while True:
        with _rate_lock:
            now = time.monotonic()
            _prune_windows(now)
            qpm_ok = len(_rate_window) < _RATE_LIMIT_PER_MIN
            tpm_ok = _tokens_in_window() + token_estimate <= _TOKEN_LIMIT_PER_MIN
            if qpm_ok and tpm_ok:
                _rate_window.append(now)
                _token_window.append((now, token_estimate))
                return
            waits: list[float] = []
            if not qpm_ok and _rate_window:
                waits.append(60.0 - (now - _rate_window[0]) + 0.05)
            if not tpm_ok and _token_window:
                waits.append(60.0 - (now - _token_window[0][0]) + 0.05)
            wait_for = max(0.1, min(waits) if waits else 0.5)
        time.sleep(wait_for)


def _record_actual_token_usage(actual_tokens: int) -> None:
    with _rate_lock:
        if _token_window:
            ts, _ = _token_window[-1]
            _token_window[-1] = (ts, actual_tokens)


def _estimate_token_cost(messages: list[dict[str, Any]], max_tokens: int) -> int:
    char_count = sum(len(str(m.get("content", ""))) for m in messages)
    return int(char_count / 4) + max_tokens


def _is_rate_limit_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "429" in msg or "too many requests" in msg


def _is_transient_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if any(k in name for k in ("timeout", "connection", "apierror", "internalserver", "service")):
        return True
    msg = str(exc).lower()
    return any(k in msg for k in ("timeout", "timed out", "connection", "502", "503", "504"))


def _extract_tool_calls(message: Any) -> list[dict[str, Any]] | None:
    raw = getattr(message, "tool_calls", None)
    if not raw:
        return None
    out: list[dict[str, Any]] = []
    for tc in raw:
        fn = getattr(tc, "function", None)
        name = getattr(fn, "name", None) if fn else None
        args_str = getattr(fn, "arguments", "") if fn else ""
        entry: dict[str, Any] = {
            "id": getattr(tc, "id", None),
            "name": name,
            "arguments_raw": args_str,
        }
        try:
            entry["arguments"] = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            entry["arguments"] = None
        out.append(entry)
    return out


def chat(
    messages: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call the SUT chat model with rate-limit gating and bounded retries.

    Model is LOCKED to ``DEFAULT_MODEL`` (set via ``MODEL_NAME``); passing a
    different ``model`` raises — the target model is the SUT and must not be
    varied by an evolved scaffold.
    """
    if model != DEFAULT_MODEL:
        raise RuntimeError(
            f"chat() model is locked to '{DEFAULT_MODEL}' (set via MODEL_NAME); "
            f"got model='{model}'. The scaffold must not override the target model."
        )
    estimate = _estimate_token_cost(messages, max_tokens)
    start = time.monotonic()
    deadline = start + _MAX_WALL_SECONDS
    last_exc: BaseException | None = None
    create_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        create_kwargs["tools"] = tools
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
    for attempt in range(1, _MAX_API_ATTEMPTS + 1):
        _wait_for_cooldown(deadline)
        _acquire_rate_slot(token_estimate=estimate, deadline=deadline)
        try:
            resp = _client.chat.completions.create(
                **create_kwargs,
                timeout=_PER_CALL_TIMEOUT,
            )
        except TypeError:
            resp = _client.chat.completions.create(**create_kwargs)
        except BaseException as e:  # noqa: BLE001 — classify then re-raise/retry
            last_exc = e
            if attempt >= _MAX_API_ATTEMPTS:
                raise
            is_rl = _is_rate_limit_error(e)
            if not (_is_transient_error(e) or is_rl):
                raise
            if is_rl:
                cooldown = min(15.0 * (2 ** (attempt - 1)), 90.0)
                cooldown *= 0.8 + 0.4 * random.random()
                _set_cooldown(cooldown)
            backoff = min(2.0 * (2 ** (attempt - 1)), 30.0)
            backoff *= 0.5 + random.random()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(backoff, max(0.0, remaining)))
            continue
        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        actual = getattr(usage, "total_tokens", None) if usage else None
        if actual:
            _record_actual_token_usage(int(actual))
        content = choice.message.content or ""
        reasoning_content = getattr(choice.message, "reasoning_content", None) or ""
        tool_calls = _extract_tool_calls(choice.message)
        assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning_content:
            assistant_message["reasoning_content"] = reasoning_content
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments_raw"],
                    },
                }
                for tc in tool_calls
            ]
        return {
            "model": model,
            "content": content,
            "reasoning_content": reasoning_content,
            "finish_reason": choice.finish_reason,
            "tool_calls": tool_calls,
            "assistant_message": assistant_message,
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
            },
        }
    if last_exc:
        raise last_exc
    raise RuntimeError("chat() exhausted attempts without exception")
