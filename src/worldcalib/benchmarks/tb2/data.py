"""Terminal-Bench 2.0 task loading for the paper's frozen split."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from worldcalib.paths import package_json, resolve_external_path
from worldcalib.runners.harbor import HarborTask
from worldcalib.schemas import LocomoExample


DEFAULT_TB2_DATASET: Path | None = None
PAPER_TRAIN_COUNT = 20
PAPER_TEST_COUNT = 67
# The paper's sandbox provider cannot provision the sole 30 GB test task.
PAPER_SANDBOX_STORAGE_CAP_MB = 20_000


@lru_cache(maxsize=1)
def load_split() -> dict[str, list[str]]:
    payload = package_json("worldcalib.benchmarks.tb2", "split.json")
    if not isinstance(payload, dict):
        raise ValueError("invalid Terminal-Bench split resource")
    train = _ids(payload, "train")
    test = _ids(payload, "test")
    if (len(train), len(test)) != (PAPER_TRAIN_COUNT, PAPER_TEST_COUNT):
        raise ValueError(
            f"invalid Terminal-Bench paper split: train={len(train)}, test={len(test)}"
        )
    if len(train) != len(set(train)) or len(test) != len(set(test)):
        raise ValueError("Terminal-Bench split contains duplicate task IDs")
    if set(train) & set(test):
        raise ValueError("Terminal-Bench train/test task IDs overlap")
    return {"train": train, "test": test}


def dataset_root(explicit: Path | str | None = None) -> Path:
    return resolve_external_path(
        explicit,
        env_var="TB2_TASKS_PATH",
        label="Terminal-Bench 2.0 task directory",
    )


def task_dir_of(dataset: Path, task_id: str) -> Path:
    return Path(dataset) / task_id


def read_solution(dataset: Path, task_id: str, *, max_chars: int = 8000) -> str:
    """Read reference-solution evidence for post-evaluation diagnosis only."""

    solution_dir = task_dir_of(dataset, task_id) / "solution"
    if not solution_dir.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(solution_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"[{path.relative_to(solution_dir)}]\n{body.strip()}")
    text = "\n\n".join(parts)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... (truncated)"


def load_tb2_tasks(
    dataset: Path | str | None = None,
    *,
    split: str = "train",
    limit: int = 0,
    task_ids: tuple[str, ...] = (),
    max_storage_mb: int = PAPER_SANDBOX_STORAGE_CAP_MB,
) -> list[HarborTask]:
    """Load Harbor tasks; by default exclude requests above the paper's cap."""

    root = dataset_root(dataset)
    if task_ids:
        wanted = list(task_ids)
    else:
        frozen = load_split()
        if split not in frozen:
            raise ValueError(f"split must be one of {sorted(frozen)}, got {split!r}")
        wanted = frozen[split]

    tasks: list[HarborTask] = []
    for task_id in wanted:
        task_dir = root / task_id
        if not (task_dir / "task.toml").is_file():
            raise FileNotFoundError(
                f"frozen split names {task_id!r}, but {task_dir} lacks task.toml"
            )
        task = HarborTask.from_task_dir(task_dir)
        if max_storage_mb > 0 and task.storage_mb > max_storage_mb:
            continue
        tasks.append(task)
    return tasks[:limit] if limit > 0 else tasks


def load_tb2_examples(
    dataset: Path | str | None = None,
    *,
    split: str = "train",
    limit: int = 0,
    max_storage_mb: int = PAPER_SANDBOX_STORAGE_CAP_MB,
) -> list[LocomoExample]:
    root = dataset_root(dataset)
    tasks = load_tb2_tasks(
        root, split=split, limit=limit, max_storage_mb=max_storage_mb
    )
    return [
        LocomoExample(
            task_id=f"tb2#{task.task_id}",
            sample_id=task.task_id,
            question=task.instruction,
            answer=read_solution(root, task.task_id),
            category=0,
            evidence=(),
            conversation=(),
            metadata={
                "benchmark": "tb2",
                "task_id": task.task_id,
                "split": split,
                "question_type": "all",
                "task_path": str(task.path),
                "agent_timeout_sec": task.agent_timeout_sec,
            },
        )
        for task in tasks
    ]


def _ids(payload: dict, key: str) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise ValueError(f"Terminal-Bench split lacks {key!r} list")
    return [str(item) for item in values]


__all__ = [
    "DEFAULT_TB2_DATASET",
    "PAPER_SANDBOX_STORAGE_CAP_MB",
    "PAPER_TEST_COUNT",
    "PAPER_TRAIN_COUNT",
    "dataset_root",
    "load_split",
    "load_tb2_examples",
    "load_tb2_tasks",
]
