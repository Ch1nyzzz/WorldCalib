"""Spider2-lite task data for the paper's database-disjoint split."""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

from worldcalib.paths import package_json, resolve_external_path
from worldcalib.schemas import LocomoExample


PAPER_TRAIN_COUNT = 31
PAPER_TEST_COUNT = 104


def spider2_root(explicit: Path | str | None = None) -> Path:
    """Resolve the external ``spider2-lite`` checkout."""

    return resolve_external_path(
        explicit,
        env_var="SPIDER2_ROOT",
        label="Spider2-lite checkout",
    )


def db_path_of(db: str, *, root: Path | str | None = None) -> Path:
    return spider2_root(root) / "resource" / "databases" / f"{db}.sqlite"


@lru_cache(maxsize=256)
def _schema_of(db: str, root_text: str) -> str:
    path = Path(root_text) / "resource" / "databases" / f"{db}.sqlite"
    if not path.exists():
        return ""
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(row[0] for row in rows if row and row[0])


def schema_of(db: str, *, root: Path | str | None = None) -> str:
    return _schema_of(db, str(spider2_root(root)))


@lru_cache(maxsize=4)
def _rows_by_id(root_text: str) -> dict[str, dict[str, Any]]:
    path = Path(root_text) / "spider2-lite.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"Spider2-lite task file not found: {path}")
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["instance_id"])] = row
    return rows


def load_split() -> dict[str, list[str]]:
    payload: Any = package_json("worldcalib.benchmarks.spider2", "split.json")
    if not isinstance(payload, dict):
        raise ValueError("invalid Spider2 split resource")
    train = _ids(payload, "train")
    test = _ids(payload, "test")
    if len(train) != PAPER_TRAIN_COUNT or len(test) != PAPER_TEST_COUNT:
        raise ValueError(
            f"invalid Spider2 paper split: train={len(train)}, test={len(test)}"
        )
    if len(train) != len(set(train)) or len(test) != len(set(test)):
        raise ValueError("Spider2 split contains duplicate ids")
    if set(train) & set(test):
        raise ValueError("Spider2 train/test ids overlap")
    return {"train": train, "test": test}


def load_spider2_examples(
    split: str = "train",
    *,
    limit: int = 0,
    root: Path | str | None = None,
) -> list[LocomoExample]:
    """Load paper-split Spider2-lite examples from an external checkout."""

    frozen = load_split()
    if split == "train":
        ids = frozen["train"]
    elif split == "test":
        ids = frozen["test"]
    elif split == "all":
        ids = [*frozen["train"], *frozen["test"]]
    else:
        raise ValueError(f"unsupported Spider2 split: {split!r}")
    if limit:
        ids = ids[:limit]

    rows = _rows_by_id(str(spider2_root(root)))
    missing = [instance_id for instance_id in ids if instance_id not in rows]
    if missing:
        raise ValueError(f"Spider2 checkout lacks split ids: {missing[:5]}")
    return [_to_example(rows[instance_id], instance_id, split) for instance_id in ids]


def _to_example(
    row: dict[str, Any], instance_id: str, split: str
) -> LocomoExample:
    return LocomoExample(
        task_id=f"spider2#{instance_id}",
        sample_id=instance_id,
        question=str(row["question"]),
        answer="",
        category=0,
        evidence=(),
        conversation=(),
        metadata={
            "domain": "spider2",
            "split": split,
            "question_type": "all",
            "instance_id": instance_id,
            "db": row["db"],
            "external_knowledge": row.get("external_knowledge") or "",
        },
    )


def _ids(payload: dict[str, Any], key: str) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise ValueError(f"Spider2 split lacks {key!r} list")
    return [str(item) for item in values]


__all__ = [
    "PAPER_TEST_COUNT",
    "PAPER_TRAIN_COUNT",
    "db_path_of",
    "load_spider2_examples",
    "load_split",
    "schema_of",
    "spider2_root",
]
