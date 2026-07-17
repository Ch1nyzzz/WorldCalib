"""Terminal-Bench 2.0 task data as ``LocomoExample``s.

Each task is one Harbor task directory — ``instruction.md`` (the brief the agent
is given), ``task.toml`` (resources / timeouts), ``tests/`` (the verifier) and
``solution/`` (the reference solution). The layout is byte-compatible with
AutoLab's, so :class:`worldcalib.autolab.autolab.AutolabTask` parses it as-is
(verified: 89/89 tasks load).

Splits: the frozen ``data/tb2/split.json`` carries ``{"train": [...], "test":
[...]}``. It is not a fresh split — it **reproduces putty's** exactly (seeded
sha256 hash-bucketing, ``seed=1729``, ``search_fraction=0.28``, then
``search_limit=20``), verified set-equal against the tasks putty's
``terminalbench_c0_v1`` baseline actually ran, so results here and there are
directly comparable. Note the two tasks the ``search_limit`` cut fall in neither
pool; that is putty's behaviour, kept deliberately.

This module is grading-side (never copied into a candidate snapshot), so it may
read repo paths directly.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from worldcalib.autolab.autolab import AutolabTask
from worldcalib.schemas import LocomoExample

# tb2 → worldcalib → src → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FROZEN_SPLIT = _REPO_ROOT / "data" / "tb2" / "split.json"

DEFAULT_TB2_DATASET = Path(
    "/data/home/yuhan/putty/runs/terminalbench_traceunit_v1"
    "/benchmark_data/terminalbench/dataset"
)


@lru_cache(maxsize=1)
def _frozen_split() -> dict[str, list[str]]:
    payload = json.loads(_FROZEN_SPLIT.read_text(encoding="utf-8"))
    return {
        "train": [str(t) for t in payload.get("train", [])],
        "test": [str(t) for t in payload.get("test", [])],
    }


def task_dir_of(dataset: Path, task_id: str) -> Path:
    """The Harbor task directory for ``task_id``."""

    return Path(dataset) / task_id


def read_solution(dataset: Path, task_id: str, *, max_chars: int = 8000) -> str:
    """The task's reference solution — gold.

    Gold rides the proposer's record (never the agent's): a terminal rollout that
    fails its tests is unreadable without knowing what the intended approach was,
    and telling "solved a different problem" from "solved the right problem badly"
    is the whole diagnosis. It says WHAT, not HOW to make the agent find it.
    """

    sol_dir = task_dir_of(dataset, task_id) / "solution"
    if not sol_dir.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(sol_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"[{path.relative_to(sol_dir)}]\n{body.strip()}")
    text = "\n\n".join(parts)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated)"


def load_tb2_tasks(
    dataset: Path | None = None,
    *,
    split: str = "train",
    limit: int = 0,
    task_ids: tuple[str, ...] = (),
) -> list[AutolabTask]:
    """Harbor task rows for a frozen split (or an explicit ``task_ids`` set)."""

    root = Path(dataset or DEFAULT_TB2_DATASET)
    if not root.is_dir():
        raise FileNotFoundError(f"Terminal-Bench 2 dataset not found at {root}")

    if task_ids:
        wanted = list(task_ids)
    else:
        frozen = _frozen_split()
        if split not in frozen:
            raise ValueError(f"split must be one of {sorted(frozen)} (got {split!r})")
        wanted = frozen[split]

    tasks: list[AutolabTask] = []
    for task_id in wanted:
        task_dir = root / task_id
        if not (task_dir / "task.toml").is_file():
            raise FileNotFoundError(
                f"frozen split names {task_id!r} but {task_dir} has no task.toml"
            )
        tasks.append(AutolabTask.from_task_dir(task_dir))
    return tasks[:limit] if limit > 0 else tasks


def load_tb2_examples(
    dataset: Path | None = None,
    *,
    split: str = "train",
    limit: int = 0,
) -> list[LocomoExample]:
    """The split's tasks as ``LocomoExample``s.

    ``question`` is the instruction the agent actually receives and ``answer`` is
    the reference solution, so the record the proposer reads carries both without
    the runner having to reach back into the dataset.
    """

    root = Path(dataset or DEFAULT_TB2_DATASET)
    tasks = load_tb2_tasks(root, split=split, limit=limit)
    examples: list[LocomoExample] = []
    for task in tasks:
        examples.append(
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
                    # Terminal-Bench has no global task-type axis, so the
                    # per-category breakdown collapses to one bucket.
                    "question_type": "all",
                    "task_path": str(task.path),
                    "agent_timeout_sec": task.agent_timeout_sec,
                },
            )
        )
    return examples
