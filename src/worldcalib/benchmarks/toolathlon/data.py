"""Toolathlon task metadata from the committed diagnostic split."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcalib.paths import package_json


TASKS_SUBDIR = "finalpool"
PAPER_TRAIN_COUNT = 36
PAPER_TEST_COUNT = 64
EXCLUDED_COUNT = 8


@dataclass(frozen=True)
class ToolathlonTask:
    """One Toolathlon finalpool task."""

    task_id: str
    app: str
    servers: tuple[str, ...]
    split: str = "train"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_dir_arg(self) -> str:
        return f"{TASKS_SUBDIR}/{self.task_id}"


def load_split() -> dict[str, Any]:
    """Load and validate the packaged 36/64 split plus eight exclusions."""

    payload = package_json("worldcalib.benchmarks.toolathlon", "split.json")
    if not isinstance(payload, dict):
        raise ValueError("invalid Toolathlon split resource")
    train = _ids(payload, "train")
    test = _ids(payload, "test")
    excluded = _ids(payload, "excluded")
    if (len(train), len(test), len(excluded)) != (
        PAPER_TRAIN_COUNT,
        PAPER_TEST_COUNT,
        EXCLUDED_COUNT,
    ):
        raise ValueError(
            "invalid Toolathlon split counts: "
            f"{len(train)}/{len(test)}/{len(excluded)}"
        )
    all_ids = [*train, *test, *excluded]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Toolathlon train/test/excluded sets overlap or contain duplicates")
    return payload


def load_toolathlon_tasks(
    split: str = "train", *, limit: int = 0
) -> list[ToolathlonTask]:
    """Return train, test, or all evaluable tasks; exclusions are never run."""

    payload = load_split()
    if split == "train":
        ids = _ids(payload, "train")
    elif split == "test":
        ids = _ids(payload, "test")
    elif split == "all":
        ids = [*_ids(payload, "train"), *_ids(payload, "test")]
    else:
        raise ValueError(f"unsupported Toolathlon split: {split!r}")
    if limit:
        ids = ids[:limit]

    per_instance = (payload.get("_meta") or {}).get("per_instance") or {}
    tasks: list[ToolathlonTask] = []
    for task_id in ids:
        info = per_instance.get(task_id, {})
        servers = tuple(str(item) for item in (info.get("servers") or ()))
        tasks.append(
            ToolathlonTask(
                task_id=task_id,
                app=str(info.get("app") or "all"),
                servers=servers,
                split=split,
                metadata={
                    "app": info.get("app"),
                    "servers": list(servers),
                },
            )
        )
    return tasks


def _ids(payload: dict[str, Any], key: str) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise ValueError(f"Toolathlon split lacks {key!r} list")
    return [str(item) for item in values]


__all__ = [
    "EXCLUDED_COUNT",
    "PAPER_TEST_COUNT",
    "PAPER_TRAIN_COUNT",
    "TASKS_SUBDIR",
    "ToolathlonTask",
    "load_split",
    "load_toolathlon_tasks",
]
