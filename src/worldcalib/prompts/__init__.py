"""Load self-contained proposer skills from package resources."""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files
from importlib.resources.abc import Traversable


_FRONTMATTER_DELIM = "---\n"
_INCLUDE_RE = re.compile(
    r"[ \t]*<!-- INCLUDE:[ \t]*([\w./-]+)[ \t]*-->[ \t]*\n?"
)


def _skills_root() -> Traversable:
    return files("worldcalib.prompts").joinpath("skills")


def _skill_resource(skill_key: str) -> Traversable:
    return _skills_root().joinpath(*skill_key.split("/"), "SKILL.md")


def _strip_frontmatter(text: str) -> str:
    if not text.startswith(_FRONTMATTER_DELIM):
        return text
    end = text.find("\n" + _FRONTMATTER_DELIM, len(_FRONTMATTER_DELIM))
    if end < 0:
        return text
    return text[end + len("\n" + _FRONTMATTER_DELIM):]


def _resolve_includes(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        relative = match.group(1)
        resource = _skills_root().joinpath(*relative.split("/"))
        if not resource.is_file():
            raise FileNotFoundError(f"prompt fragment is missing: {relative}")
        fragment = _strip_frontmatter(resource.read_text(encoding="utf-8"))
        if _INCLUDE_RE.search(fragment):
            raise ValueError(f"nested prompt include is unsupported: {relative}")
        return fragment.strip("\n") + "\n"

    return _INCLUDE_RE.sub(replace, text)


def benchmark_skill_name(*, benchmark_name: str, target_system: str) -> str:
    """Map a supported paper benchmark to its prompt key."""

    benchmark = benchmark_name.lower()
    target = target_system.lower()
    if "terminal-bench 2" in benchmark or "tb2" in benchmark or "tb2" in target:
        return "tb2"
    if "spider2" in benchmark or "spider2" in target:
        return "spider2"
    if "toolathlon" in benchmark or "toolathlon" in target:
        return "toolathlon"
    if "appworld" in benchmark or "appworld" in target:
        return "appworld"
    if "gaia" in benchmark or "gaia" in target:
        return "gaia"
    if "longmemeval" in benchmark:
        return "longmemeval"
    if "locomo" in benchmark:
        return "locomo"
    raise ValueError(
        f"no proposer skill is registered for benchmark={benchmark_name!r}, "
        f"target_system={target_system!r}"
    )


@lru_cache(maxsize=32)
def load_proposer_skill(skill_key: str) -> str:
    """Return one resolved proposer skill without YAML frontmatter."""

    resource = _skill_resource(skill_key)
    if not resource.is_file():
        raise FileNotFoundError(f"proposer skill is missing: {skill_key}")
    raw = resource.read_text(encoding="utf-8")
    return _strip_frontmatter(_resolve_includes(raw)).rstrip() + "\n"


def proposer_skill_path(skill_key: str) -> Traversable:
    """Return the package resource for one unresolved proposer skill."""

    return _skill_resource(skill_key)


__all__ = [
    "benchmark_skill_name",
    "load_proposer_skill",
    "proposer_skill_path",
]
