"""GAIA Level 1/2 data loading with the paper's deterministic split."""

from __future__ import annotations

import os
from collections.abc import Iterator

from worldcalib.schemas import LocomoExample


GAIA_DATASET = "gaia-benchmark/GAIA"
GAIA_CONFIG = "2023_all"
# Pin the exact Hub snapshot used to make ordinal task selection reproducible.
GAIA_REVISION = "682dd723ee1e1697e00360edccf2366dc8418dd9"
DEFAULT_LEVELS: tuple[int, ...] = (1, 2)
PAPER_TRAIN_SIZE = 40
PAPER_TEST_SIZE = 99


def iter_tasks(
    split: str = "validation", levels: tuple[int, ...] | None = None
) -> Iterator[dict]:
    """Yield raw GAIA tasks from the pinned Hugging Face revision."""

    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "GAIA requires the optional 'gaia' dependencies: "
            "pip install 'worldcalib[gaia]'"
        ) from exc

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    dataset = load_dataset(
        GAIA_DATASET,
        GAIA_CONFIG,
        split=split,
        revision=GAIA_REVISION,
        token=token,
    )
    for row in dataset:
        level = row.get("Level")
        try:
            level_int = int(level)
        except (TypeError, ValueError):
            continue
        if levels is not None and level_int not in levels:
            continue
        yield {
            "task_id": row["task_id"],
            "question": row["Question"],
            "level": level_int,
            "final_answer": row.get("Final answer", ""),
            "file_name": row.get("file_name", "") or "",
        }


def build_prompt(task: dict) -> str:
    """Build the user turn, including the attachment hint when present."""

    if task.get("file_name"):
        return (
            f"{task['question']}\n\n"
            f"[A file '{task['file_name']}' is attached. "
            f"Use the file_read tool with file_name='{task['file_name']}' to read it.]"
        )
    return str(task["question"])


def _to_example(task: dict, split: str) -> LocomoExample:
    level = int(task["level"])
    gaia_id = str(task["task_id"])
    return LocomoExample(
        task_id=f"gaia#{gaia_id}",
        sample_id=gaia_id,
        question=build_prompt(task),
        answer=str(task.get("final_answer") or ""),
        category=level,
        evidence=(),
        conversation=(),
        metadata={
            "domain": "gaia",
            "split": split,
            "question_type": f"level_{level}",
            "gaia_task_id": gaia_id,
            "level": level,
            "file_name": task.get("file_name") or "",
            "dataset_revision": GAIA_REVISION,
        },
    )


def load_gaia_examples(
    split: str = "train",
    *,
    levels: tuple[int, ...] = DEFAULT_LEVELS,
    train_size: int = PAPER_TRAIN_SIZE,
    test_size: int = PAPER_TEST_SIZE,
    limit: int = 0,
) -> list[LocomoExample]:
    """Return the paper split: first 40 L1/L2 tasks, then the remaining 99."""

    if split not in {"train", "test"}:
        raise ValueError(f"GAIA split must be 'train' or 'test', got {split!r}")
    raw = list(iter_tasks(split="validation", levels=levels))
    expected = train_size + test_size
    if len(raw) != expected:
        raise ValueError(
            f"pinned GAIA L1/L2 set has {len(raw)} tasks; expected {expected} "
            "for the paper's 40/99 split"
        )
    chosen = raw[:train_size] if split == "train" else raw[train_size:expected]
    if limit:
        chosen = chosen[:limit]
    return [_to_example(task, split) for task in chosen]


__all__ = [
    "DEFAULT_LEVELS",
    "GAIA_REVISION",
    "PAPER_TEST_SIZE",
    "PAPER_TRAIN_SIZE",
    "build_prompt",
    "iter_tasks",
    "load_gaia_examples",
]
