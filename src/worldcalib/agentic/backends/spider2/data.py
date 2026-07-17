"""Spider2-lite (local sqlite subset) task data as ``LocomoExample``s.

Each task is one text-to-SQL instance graded by executing the predicted SQL
against the bundled sqlite DB and comparing to the gold result table (see
:mod:`worldcalib.agentic.backends.spider2.scorer`). The ``LocomoExample`` carries
the question; ``metadata`` holds the per-category axis (``question_type`` —
currently a single ``"all"`` bucket, since Spider2-lite has no usable global
task-type) plus the ``instance_id``, ``db`` and ``external_knowledge`` fields.

Splits: the frozen ``data/spider2/lite_local_split.json`` carries
``{"train": [...instance_ids], "test": [...instance_ids]}`` (db-disjoint, train
baseline pass-rate ≈ 0.29), making the ids reproducible across the WMC / no-WMC
arms.

This module is grading-side (never copied into a candidate snapshot), so it may
read repo paths directly.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from worldcalib.schemas import LocomoExample

# spider2 → backends → agentic → worldcalib → src → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[5]
_LITE_ROOT = _REPO_ROOT / "third_party" / "Spider2" / "spider2-lite"
_LITE_JSONL = _LITE_ROOT / "spider2-lite.jsonl"
_DB_DIR = _LITE_ROOT / "resource" / "databases"
_FROZEN_SPLIT = _REPO_ROOT / "data" / "spider2" / "lite_local_split.json"


def db_path_of(db: str) -> Path:
    """Absolute path to a database's sqlite file."""
    return _DB_DIR / f"{db}.sqlite"


@lru_cache(maxsize=256)
def schema_of(db: str) -> str:
    """The database DDL (``CREATE TABLE`` statements) for prompt grounding."""
    path = db_path_of(db)
    if not path.exists():
        return ""
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(r[0] for r in rows if r and r[0])


@lru_cache(maxsize=1)
def _rows_by_id() -> dict[str, dict]:
    rows = {}
    for line in _LITE_JSONL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["instance_id"]] = row
    return rows


def _to_example(instance_id: str, split: str) -> LocomoExample:
    row = _rows_by_id()[instance_id]
    return LocomoExample(
        task_id=f"spider2#{instance_id}",
        sample_id=instance_id,
        question=row["question"],
        answer="",  # graded by execution against the gold result table, not a string
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


def load_spider2_examples(
    split: str = "train",
    *,
    limit: int = 0,
) -> list[LocomoExample]:
    """Load Spider2-lite local examples for ``split`` ("train"/"test").

    Reads the frozen db-disjoint split; raises if it is missing (the split is a
    committed artifact, not something to regenerate on the fly).
    """
    if not _FROZEN_SPLIT.exists():
        raise FileNotFoundError(
            f"frozen Spider2 split not found at {_FROZEN_SPLIT}; "
            "build it with scripts/build_spider2_lite_split.py"
        )
    frozen = json.loads(_FROZEN_SPLIT.read_text())
    if split in ("train", "test"):
        ids = list(frozen.get(split, []))
    else:
        ids = list(frozen.get("train", [])) + list(frozen.get("test", []))
    if limit:
        ids = ids[:limit]
    return [_to_example(i, split) for i in ids]
