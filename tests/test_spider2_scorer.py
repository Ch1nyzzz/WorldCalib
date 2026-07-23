"""Spider2 scorer integration against an explicit external checkout."""

from __future__ import annotations

from worldcalib.benchmarks.spider2.scorer import score_sql


def test_score_sql_uses_explicit_checkout(tmp_path) -> None:
    suite = tmp_path / "evaluation_suite"
    gold_results = suite / "gold" / "exec_result"
    databases = tmp_path / "resource" / "databases"
    gold_results.mkdir(parents=True)
    databases.mkdir(parents=True)

    (suite / "evaluate.py").write_text(
        """
from pathlib import Path


def load_jsonl_to_dict(path):
    assert Path(path).is_file()
    return {"local001": {}}


def resolve_gold_paths(instance_id, gold_result_dir):
    return [str(Path(gold_result_dir) / f"{instance_id}.csv")], True


def evaluate_single_sql_instance(
    instance_id,
    eval_standard,
    metadata,
    pred_dir,
    gold_result_dir,
    *,
    temp_dir,
    result_csv_dir,
    timeout,
    sqlite_base_dir,
):
    assert instance_id in eval_standard
    assert instance_id in metadata
    assert (Path(pred_dir) / f"{instance_id}.sql").read_text() == "SELECT 1"
    assert Path(sqlite_base_dir).name == "databases"
    out = Path(result_csv_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{instance_id}.csv").write_text("value\\n1\\n")
    return {"score": 1, "error_info": None}
""".lstrip(),
        encoding="utf-8",
    )
    (suite / "gold" / "spider2lite_eval.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    (tmp_path / "spider2-lite.jsonl").write_text("{}\n", encoding="utf-8")
    (gold_results / "local001.csv").write_text("value\n1\n", encoding="utf-8")

    grade = score_sql("local001", "SELECT 1", root=tmp_path)

    assert grade.passed is True
    assert grade.error is None
    assert "1 row(s)" in grade.result_preview
    assert "[local001]" in grade.gold_preview
