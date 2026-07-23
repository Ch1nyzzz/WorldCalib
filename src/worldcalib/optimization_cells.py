"""Optional prompt-guided optimization cells for memory scaffolds."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizationCell:
    name: str
    target_system: str
    description: str
    focus_functions: tuple[str, ...]
    prompt_guidance: str


MEMGPT_OPTIMIZATION_CELLS = {
    "core_summary": OptimizationCell(
        name="core_summary",
        target_system="memgpt",
        description="Optimize core-memory construction and compaction.",
        focus_functions=(
            "_build_core_memory",
            "_build_summary_message",
            "_compile_core_memory",
            "_compile_memory_metadata",
        ),
        prompt_guidance="Focus on stable memory and compressed history representation.",
    ),
    "memory_representation": OptimizationCell(
        name="memory_representation",
        target_system="memgpt",
        description="Optimize conversion of turns into recall and archival memory.",
        focus_functions=(
            "MemGPTSourceScaffold.build",
            "_build_recall_messages",
            "_build_archival_passages",
        ),
        prompt_guidance="Focus on message transformation, chunking, and representation.",
    ),
    "retrieval_policy": OptimizationCell(
        name="retrieval_policy",
        target_system="memgpt",
        description="Optimize memory mixing, ranking, expansion, and deduplication.",
        focus_functions=(
            "MemGPTSourceScaffold.retrieve",
            "_hybrid_rank",
            "_expand_recall_indices",
            "_dedupe_hits",
            "_core_hit",
        ),
        prompt_guidance="Focus on retrieval and evidence assembly, not scalar tuning.",
    ),
    "all": OptimizationCell(
        name="all",
        target_system="memgpt",
        description="Redesign across memory construction and retrieval.",
        focus_functions=(),
        prompt_guidance="Fuse mechanisms across cells when the evidence justifies it.",
    ),
}


def get_target_cells(target_system: str) -> list[OptimizationCell]:
    if target_system.strip().lower() == "memgpt":
        return list(MEMGPT_OPTIMIZATION_CELLS.values())
    return []


def get_cell(name: str, target_system: str = "memgpt") -> OptimizationCell:
    if target_system.strip().lower() != "memgpt":
        raise KeyError(f"unknown target system: {target_system}")
    try:
        return MEMGPT_OPTIMIZATION_CELLS[name]
    except KeyError as exc:
        raise KeyError(f"unknown memgpt optimization cell: {name}") from exc


__all__ = [
    "MEMGPT_OPTIMIZATION_CELLS",
    "OptimizationCell",
    "get_cell",
    "get_target_cells",
]
