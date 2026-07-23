"""Spider2 backend — single-shot text-to-SQL over the locked DeepSeek SUT.

Built-in scaffolds are looked up by name via :func:`build_spider2_scaffold`; the
seed (``spider2_passthrough``) is the editable capability layer the optimizer's
proposer evolves.
"""

from __future__ import annotations

from worldcalib.benchmarks.spider2.base import Spider2Scaffold
from worldcalib.benchmarks.spider2.seed_passthrough import (
    PassthroughSpider2Scaffold,
)

DEFAULT_SPIDER2_SEED_SCAFFOLDS: tuple[str, ...] = ("spider2_passthrough",)

_REGISTRY: dict[str, type[Spider2Scaffold]] = {
    "spider2_passthrough": PassthroughSpider2Scaffold,
}


def build_spider2_scaffold(name: str) -> Spider2Scaffold:
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown spider2 scaffold {name!r}; known: {sorted(_REGISTRY)}"
        ) from exc
    return cls()


__all__ = [
    "Spider2Scaffold",
    "PassthroughSpider2Scaffold",
    "DEFAULT_SPIDER2_SEED_SCAFFOLDS",
    "build_spider2_scaffold",
]
