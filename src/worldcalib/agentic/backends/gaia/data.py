"""GAIA task data — load the gated HF GAIA validation set as ``LocomoExample``s.

GAIA tasks are agentic (a question + optional attached file, graded by exact
match against ``final_answer``), so the ``LocomoExample`` carries the question
text and gold answer directly; ``metadata`` holds the per-category axis
(``question_type = "level_<n>"``) the self-distill prediction protocol reads,
plus the gaia ``task_id``, ``level`` and ``file_name``.

Splits: an optional frozen ``data/agentic/gaia_split.json`` carrying
``{"train": [...gaia task_ids], "test": [...gaia task_ids]}`` makes the
train/test ids fully reproducible across the WMC / no-WMC arms. When absent, the
effective default is a deterministic ordinal slice over the level-filtered task
list.

The HF dataset is cached locally (``gaia-benchmark/GAIA``, ``2023_all``); loading
needs no token when the snapshot is already present.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from datasets import load_dataset

from worldcalib.schemas import LocomoExample

# gaia → backends → agentic → worldcalib → src → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[5]
_FROZEN_SPLIT = _REPO_ROOT / "data" / "agentic" / "gaia_split.json"

# L1+L2 is the chosen scope (139 of the 165 validation tasks; L3 excluded).
DEFAULT_LEVELS: tuple[int, ...] = (1, 2)


def iter_tasks(
    split: str = "validation", levels: tuple[int, ...] | None = None
) -> Iterator[dict]:
    """Iterate raw GAIA tasks (dicts: task_id, question, level, final_answer, file_name)."""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    ds = load_dataset("gaia-benchmark/GAIA", "2023_all", split=split, token=token)
    for row in ds:
        level = row.get("Level")
        try:
            level_int = int(level)
        except (TypeError, ValueError):
            level_int = level
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
    """The user-turn prompt: the question plus a file-attachment hint if any."""
    if task.get("file_name"):
        return (
            f"{task['question']}\n\n"
            f"[A file '{task['file_name']}' is attached. "
            f"Use the file_read tool with file_name='{task['file_name']}' to read it.]"
        )
    return task["question"]


def _to_example(task: dict, split: str) -> LocomoExample:
    level = task.get("level")
    level_int = level if isinstance(level, int) else 0
    gaia_id = str(task["task_id"])
    return LocomoExample(
        task_id=f"gaia#{gaia_id}",
        sample_id=gaia_id,
        question=build_prompt(task),
        answer=str(task.get("final_answer") or ""),
        category=level_int,
        evidence=(),
        conversation=(),
        metadata={
            "domain": "gaia",
            "split": split,
            "question_type": f"level_{level}",
            "gaia_task_id": gaia_id,
            "level": level,
            "file_name": task.get("file_name") or "",
        },
    )


def load_gaia_examples(
    split: str = "train",
    *,
    levels: tuple[int, ...] = DEFAULT_LEVELS,
    train_size: int = 40,
    test_size: int = 0,
    limit: int = 0,
) -> list[LocomoExample]:
    """Load GAIA examples for ``split`` ("train"/"test").

    Loads the level-filtered validation tasks (deterministic dataset order),
    then partitions into train/test by the frozen ``gaia_split.json`` when it
    exists, else by an ordinal slice (front ``train_size`` = train, the next
    ``test_size`` = test, or the remainder when ``test_size`` is 0).
    """
    raw = list(iter_tasks(split="validation", levels=levels))
    by_id = {str(t["task_id"]): t for t in raw}

    if _FROZEN_SPLIT.exists():
        frozen = json.loads(_FROZEN_SPLIT.read_text())
        ids = frozen.get(split, [])
        chosen = [by_id[i] for i in ids if i in by_id]
    else:
        if split == "train":
            chosen = raw[:train_size]
        else:  # test
            end = train_size + test_size if test_size else len(raw)
            chosen = raw[train_size:end]

    if limit:
        chosen = chosen[:limit]
    return [_to_example(t, split) for t in chosen]
