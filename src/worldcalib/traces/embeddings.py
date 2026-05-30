"""Diff embedding helper.

Wraps an OpenAI-compatible embeddings endpoint (default
``text-embedding-3-small``). The TraceHarness embeds each iteration's
``diff.patch`` after recording its spans, persisting both the raw text
and the float32 vector into ``diff_embeddings`` so the MCP-side
similarity tool can do in-memory cosine recall later.

Failures are deliberately non-fatal: if the embedding call errors or
the diff is empty, the writer logs a warning and skips. Downstream
queries simply return fewer rows.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Iterable, Sequence


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiffEmbedding:
    model: str
    dim: int
    diff_text: str
    vector: tuple[float, ...]

    def to_bytes(self) -> bytes:
        return pack_vector(self.vector)


def pack_vector(values: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: bytes, dim: int) -> tuple[float, ...]:
    return struct.unpack(f"<{dim}f", blob)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Plain cosine similarity. Inputs are short (~1500 dims), no numpy."""

    if not a or not b:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a**0.5) * (norm_b**0.5))


class DiffEmbedder:
    """OpenAI-compatible embedding client wrapper."""

    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._client = None  # lazy

    def _resolve_api_key(self) -> str | None:
        if self._api_key is not None:
            return self._api_key
        import os

        return os.environ.get("OPENAI_API_KEY")

    def _resolve_base_url(self) -> str:
        import os

        base = self._base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        return base.rstrip("/")

    def embed(self, text: str) -> DiffEmbedding | None:
        """Return embedding for `text`, or None on empty/error.

        Calls an OpenAI-compatible ``/embeddings`` endpoint over the standard
        library (``urllib``) rather than the ``openai`` SDK, so it works in
        minimal runtimes — notably the proposer docker image, which does not
        ship the SDK (a missing import there silently disabled trace_similar).

        Truncation: ``text-embedding-3-small`` accepts up to 8191 tokens; we
        cap input chars to ~32K to stay safely under that. Larger diffs get
        tail-truncated.
        """

        if not text or not text.strip():
            return None
        api_key = self._resolve_api_key()
        if not api_key:
            _LOG.warning("DiffEmbedder.embed: no OPENAI_API_KEY available")
            return None
        clipped = text if len(text) <= 32_000 else text[:32_000]

        import json
        import urllib.request

        url = f"{self._resolve_base_url()}/embeddings"
        payload = json.dumps({"model": self.model, "input": clipped}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                body = json.load(resp)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            _LOG.warning("DiffEmbedder.embed failed: %r", exc)
            return None
        try:
            vector = tuple(float(v) for v in body["data"][0]["embedding"])
        except (KeyError, IndexError, TypeError) as exc:
            _LOG.warning("DiffEmbedder: malformed response (%r)", exc)
            return None
        return DiffEmbedding(
            model=self.model,
            dim=len(vector),
            diff_text=clipped,
            vector=vector,
        )

    def embed_many(self, texts: Iterable[str]) -> list[DiffEmbedding | None]:
        return [self.embed(t) for t in texts]
