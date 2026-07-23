"""Execution-based scorer for Spider2-lite local (sqlite) predictions.

Grading semantics are Spider2's own — column-subset matching, optional
``ignore_order`` / ``condition_cols``, and multi-table gold — so we **reuse**
the official ``evaluate_single_sql_instance`` from the vendored
``spider2-lite/evaluation_suite`` rather than reimplementing the comparison. The
predicted SQL is written to a per-call temp ``<instance_id>.sql`` and the
official function executes it against the bundled sqlite DB and compares to the
gold result CSV(s).

This module is grading-side: it is never copied into a candidate snapshot, so a
candidate cannot edit how it is scored.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from worldcalib.benchmarks.spider2.data import spider2_root


def _paths(root: Path | str | None = None) -> tuple[Path, Path, Path, Path]:
    lite_root = spider2_root(root)
    eval_suite = lite_root / "evaluation_suite"
    gold_dir = eval_suite / "gold"
    return (
        lite_root,
        eval_suite,
        gold_dir,
        lite_root / "resource" / "databases",
    )


@lru_cache(maxsize=4)
def _eval_module(root_text: str) -> Any:
    """Import the vendored evaluation_suite/evaluate.py as a module (cached)."""
    _lite_root, eval_suite, _gold_dir, _db_dir = _paths(root_text)
    path = eval_suite / "evaluate.py"
    if not path.exists():
        raise FileNotFoundError(f"Spider2 evaluation suite not found at {path}")
    # The suite imports sibling helpers (evaluate_utils) by package-relative name,
    # so its directory must be importable.
    suite_dir = str(eval_suite)
    if suite_dir not in sys.path:
        sys.path.insert(0, suite_dir)
    spec = importlib.util.spec_from_file_location("spider2_evaluate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Spider2 evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["spider2_evaluate"] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=4)
def _dicts(root_text: str) -> tuple[dict, dict]:
    """(eval_standard_dict, spider2sql_metadata), loaded once."""
    mod = _eval_module(root_text)
    lite_root, _eval_suite, gold_dir, _db_dir = _paths(root_text)
    eval_standard = mod.load_jsonl_to_dict(str(gold_dir / "spider2lite_eval.jsonl"))
    metadata = mod.load_jsonl_to_dict(str(lite_root / "spider2-lite.jsonl"))
    return eval_standard, metadata


@dataclass(frozen=True)
class SqlGrade:
    """The verdict, the candidate's own returned rows, and the gold rows.

    ``result_preview`` is what the candidate's query returned; ``gold_preview`` is
    what it was graded against. **Both** are needed to diagnose: a "no helmet" group
    holding 2796 collisions looks perfectly reasonable on its own — California really
    has ~2796 motorcycle collisions — and is obviously wrong only next to a gold that
    says the group holds 1. Gold names WHAT was expected; it never says HOW to get
    there (you still have to query the DB to learn why those 2795 rows do not belong),
    so it informs the proposer without solving the task for it.

    Gold reaches the proposer's record only. It is never handed to the scaffold.
    """

    passed: bool
    error: str | None
    result_preview: str
    gold_preview: str


def _format_gold_preview(
    mod: Any, instance_id: str, gold_result_dir: Path, *, max_chars: int = 4000
) -> str:
    """Render the gold result table(s) this instance is graded against.

    Uses the suite's own ``resolve_gold_paths`` so the proposer sees exactly what the
    scorer compares to. An instance may accept several variants with different column
    layouts (``local015`` has five); showing them all also conveys the column-subset
    matching semantics, which are otherwise invisible.
    """

    try:
        paths, _is_single = mod.resolve_gold_paths(instance_id, str(gold_result_dir))
    except Exception:  # noqa: BLE001 — evidence is best-effort, grading is not
        return ""
    if not paths:
        return ""
    parts: list[str] = []
    if len(paths) > 1:
        parts.append(f"(any one of {len(paths)} accepted variants)")
    for path in paths:
        try:
            body = Path(path).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        parts.append(f"[{Path(path).stem}]\n{body}")
    text = "\n".join(parts)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... (truncated)"


def _format_result_preview(
    csv_path: Path, *, max_rows: int = 20, max_chars: int = 2000
) -> str:
    """Render the predicted result CSV as ``<n> rows`` + a capped head."""

    try:
        lines = csv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not lines:
        return "0 rows (empty result)"
    header, rows = lines[0], lines[1:]
    kept = rows[:max_rows]
    out = [f"{len(rows)} row(s)", header, *kept]
    if len(rows) > len(kept):
        out.append(f"... ({len(rows) - len(kept)} more rows)")
    text = "\n".join(out)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... (truncated)"


def score_sql(
    instance_id: str, sql: str, *, root: Path | str | None = None
) -> SqlGrade:
    """Execute ``sql`` for ``instance_id`` and grade it.

    Never raises — a broken candidate query scores 0 with the error captured.
    """
    root_path = spider2_root(root)
    root_text = str(root_path)
    mod = _eval_module(root_text)
    _lite_root, _eval_suite, gold_dir, sqlite_base_dir = _paths(root_text)
    gold_result_dir = gold_dir / "exec_result"
    gold_preview = _format_gold_preview(mod, instance_id, gold_result_dir)
    if not sql or not sql.strip():
        return SqlGrade(False, "empty SQL", "", gold_preview)
    eval_standard, metadata = _dicts(root_text)
    with tempfile.TemporaryDirectory(prefix="spider2_score_") as tmp:
        tmp_path = Path(tmp)
        pred_dir = tmp_path / "pred"
        work_dir = tmp_path / "work"
        # The official evaluator copies the prediction's own result CSV here when
        # the query executes; without it the rows die with the temp dir.
        result_dir = tmp_path / "result"
        pred_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        (pred_dir / f"{instance_id}.sql").write_text(sql, encoding="utf-8")
        try:
            out = mod.evaluate_single_sql_instance(
                instance_id,
                eval_standard,
                metadata,
                str(pred_dir),
                str(gold_result_dir),
                temp_dir=work_dir,
                result_csv_dir=str(result_dir),
                timeout=60,
                sqlite_base_dir=sqlite_base_dir,
            )
        except Exception as exc:  # noqa: BLE001 — grading must never crash the eval
            return SqlGrade(
                False, f"scorer error: {type(exc).__name__}: {exc}", "", gold_preview
            )
        # Read inside the `with`: the temp tree is gone on exit.
        preview = _format_result_preview(result_dir / f"{instance_id}.csv")
    passed = int(out.get("score", 0)) == 1
    return SqlGrade(passed, out.get("error_info"), preview, gold_preview)
