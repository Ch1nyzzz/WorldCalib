"""AgentBench task data — train/test index splits carried in LocomoExample.

Each agent "example" is one ``(task, index)`` episode. To reuse the optimizer
main loop without changing its signatures, every example is wrapped in a
``LocomoExample`` container:

- ``task_id`` / ``sample_id`` = ``f"{task}#{index}"``
- ``metadata`` = ``{"task", "index", "split", "question_type"}``

``question_type`` is the per-category axis for self-distill prediction (the
task-type). It is pre-built from each task's data file (the episode ``result``
is ``null`` for these tasks, so the category cannot come from the episode):

- DB: ``entry["type"][0]`` of ``data/dbbench/standard.jsonl``
  (other/counting/comparison/ranking/aggregation-*/INSERT/UPDATE).
- OS / alfworld: added in M3.
- webshop: no per-category source yet — falls back to a single ``"all"`` bucket.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from worldcalib.schemas import LocomoExample

AGENTBENCH_TASKS: tuple[str, ...] = ("db", "os", "alfworld", "webshop")

# Frozen train/test index splits live here, one file per task:
#   data/agentic/<task>_split.json  ->  {"train": [...indices], "test": [...indices]}
# When present, load_agentbench_examples reads the split from disk (deterministic,
# reproducible across WMC / no-WMC arms) instead of slicing the live controller
# indices. The repo root is six levels up from this file
# (agentbench/backends/agentic/worldcalib/src/worldcalib).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_FROZEN_SPLIT_DIR = _REPO_ROOT / "data" / "agentic"

_SERVER_NAME: dict[str, str] = {
    "db": "dbbench-std",
    "os": "os-std",
    "alfworld": "alfworld-std",
    "webshop": "webshop-std",
}

# WorldCalib repo root -> third_party/AgentBench (editable install layout).
# This file lives at src/worldcalib/agentic/backends/agentbench/data.py, so the
# repo root is five levels up (agentbench/backends/agentic/worldcalib/src).
_AGENTBENCH_ROOT = Path(__file__).resolve().parents[5] / "third_party" / "AgentBench"

_DATA_FILE: dict[str, str] = {
    "db": "data/dbbench/standard.jsonl",
}


def task_server_name(task: str) -> str:
    """Map the logical task (db/os/alfworld/webshop) to the AgentBench worker name."""
    try:
        return _SERVER_NAME[task]
    except KeyError as exc:
        raise KeyError(f"unknown agentbench task {task!r}; known: {AGENTBENCH_TASKS}") from exc


def task_categories(task: str) -> list[str]:
    """index -> task-type label, pre-built from the task's data file.

    Returns an empty list when no mapping is available (falls back to "all").
    """
    if task == "db":
        path = _AGENTBENCH_ROOT / _DATA_FILE["db"]
        categories: list[str] = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            raw = entry.get("type")
            label = raw[0] if isinstance(raw, list) and raw else str(raw)
            categories.append(str(label))
        return categories
    # os / alfworld pre-built in M3; webshop has no per-category source yet.
    return []


def fetch_indices(controller_url: str, server_name: str, *, timeout: float = 15.0) -> list[int]:
    """Read the registered sample indices for a task from the controller."""
    url = controller_url.rstrip("/") + "/list_workers"
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted local controller)
        data = json.load(resp)
    entry = data.get(server_name) or {}
    indices = entry.get("indices") or []
    return sorted(int(i) for i in indices)


def frozen_split_path(task: str) -> Path:
    """Path to the frozen split file for a task (may not exist)."""
    return _FROZEN_SPLIT_DIR / f"{task}_split.json"


def load_frozen_split(task: str) -> dict[str, list[int]] | None:
    """Frozen ``{"train": [...], "test": [...]}`` index split, or None if absent.

    Indices are returned in their on-disk order (deterministic, frozen at freeze
    time) so both the WMC and no-WMC arms iterate identical episodes.
    """
    path = frozen_split_path(task)
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return {
        "train": [int(i) for i in payload.get("train", [])],
        "test": [int(i) for i in payload.get("test", [])],
    }


def _make_example(task: str, index: int, split: str, category: str | None) -> LocomoExample:
    metadata: dict[str, object] = {"task": task, "index": index, "split": split}
    if category:
        metadata["question_type"] = category
    return LocomoExample(
        task_id=f"{task}#{index}",
        sample_id=f"{task}#{index}",
        question="",
        answer="",
        category=0,
        evidence=(),
        conversation=(),
        metadata=metadata,
    )


def load_agentbench_examples(
    task: str,
    split: str,
    *,
    controller_url: str,
    train_size: int,
    test_size: int,
    limit: int = 0,
) -> list[LocomoExample]:
    """Deterministic train/test split over a task's registered indices.

    Prefers the frozen split at ``data/agentic/<task>_split.json`` when present
    (reproducible, identical across WMC / no-WMC arms); otherwise falls back to
    the live ordinal slice over the controller's registered indices.
    """
    frozen = load_frozen_split(task)
    if frozen is not None:
        if split == "train":
            selected = frozen["train"]
        elif split == "test":
            selected = frozen["test"]
        else:
            selected = frozen["train"] + frozen["test"]
    else:
        all_idx = fetch_indices(controller_url, task_server_name(task))
        if split == "train":
            selected = all_idx[:train_size]
        elif split == "test":
            selected = all_idx[train_size : train_size + test_size]
        else:
            selected = all_idx
    if limit:
        selected = selected[:limit]

    categories = task_categories(task)
    return [
        _make_example(task, i, split, categories[i] if i < len(categories) else None)
        for i in selected
    ]
