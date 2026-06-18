"""Regression tests for two AutoLab two-arm fixes.

Fix A: the optimizer persists the iter-0 seed frontier as a root
``run_summary.json`` so a sibling ablation arm can reuse the exact same baseline
via ``--baseline-dir`` (``load_baseline_candidates`` reads it, filtered by the
top-level split). Previously the optimizer wrote no root ``run_summary.json``,
so ``--baseline-dir <run>`` silently loaded zero candidates.

Fix B: ``AutolabHarborRunner`` now wires ``--autolab-concurrency`` into harbor's
``-n`` (concurrent trials). It used to be hardcoded to ``"1"``, so the flag was a
silent no-op and every task's ``n_attempts`` trials ran serially.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from worldcalib.autolab.autolab import AutolabHarborRunner, AutolabTask
from worldcalib.baseline import load_baseline_candidates
from worldcalib.optimizer import LocomoOptimizer
from worldcalib.schemas import CandidateResult


def _seed_candidate(count: int = 10) -> CandidateResult:
    return CandidateResult.from_dict(
        {
            "candidate_id": "iter000_terminus2_autolab",
            "scaffold_name": "terminus2_autolab",
            "count": count,
            "passrate": 0.0,
            "average_score": 0.4,
            "token_consuming": 0,
            "avg_token_consuming": 0,
            "avg_prompt_tokens": 0,
            "avg_completion_tokens": 0,
            "result_path": "",
            "config": {"name": "terminus2_autolab", "scaffold_name": "terminus2_autolab"},
        }
    )


def test_seed_run_summary_is_reusable_as_baseline(tmp_path: Path) -> None:
    """Fix A: the run_summary.json the optimizer writes loads back as a seed."""
    run_dir = tmp_path / "calib_run"
    run_dir.mkdir()
    fake = SimpleNamespace(
        run_dir=run_dir,
        config=SimpleNamespace(run_id="calib_run", split="train", limit=0),
    )
    # Call the real helper bound to our minimal stand-in.
    LocomoOptimizer._write_seed_run_summary(fake, [_seed_candidate(10)])

    summary = run_dir / "run_summary.json"
    assert summary.exists()
    payload = json.loads(summary.read_text())
    assert payload["split"] == "train"
    assert payload["candidate_count"] == 1

    got = load_baseline_candidates(run_dir, split="train", scaffolds=["terminus2_autolab"])
    assert len(got) == 1
    assert int(got[0]["count"]) == 10
    assert got[0]["scaffold_name"] == "terminus2_autolab"

    # Split filter must reject a mismatched split.
    assert load_baseline_candidates(run_dir, split="test", scaffolds=["terminus2_autolab"]) == []


def test_seed_run_summary_not_overwritten(tmp_path: Path) -> None:
    """Re-invoking the helper must not clobber an existing baseline summary."""
    run_dir = tmp_path / "calib_run"
    run_dir.mkdir()
    fake = SimpleNamespace(
        run_dir=run_dir,
        config=SimpleNamespace(run_id="calib_run", split="train", limit=0),
    )
    LocomoOptimizer._write_seed_run_summary(fake, [_seed_candidate(10)])
    LocomoOptimizer._write_seed_run_summary(fake, [])  # would write candidate_count=0 if it overwrote
    payload = json.loads((run_dir / "run_summary.json").read_text())
    assert payload["candidate_count"] == 1


def test_harbor_argv_honours_concurrency(tmp_path: Path) -> None:
    """Fix B: -n reflects --autolab-concurrency instead of a hardcoded 1."""
    task = AutolabTask(task_id="aes128_ctr", instruction="opt", path=tmp_path / "aes128_ctr")
    runner = AutolabHarborRunner(
        tasks=[task],
        out_dir=tmp_path / "out",
        n_attempts=3,
        concurrency=3,
    )
    argv = runner._build_argv(
        task=task,
        candidate={"model": "openai/deepseek-v4-flash"},
        jobs_dir=tmp_path / "jobs",
        job_name="terminus2_autolab__aes128_ctr",
    )
    # -k = attempts per trial, -n = concurrent trials.
    assert "-k" in argv and argv[argv.index("-k") + 1] == "3"
    assert "-n" in argv and argv[argv.index("-n") + 1] == "3"

    serial = AutolabHarborRunner(
        tasks=[task], out_dir=tmp_path / "out2", n_attempts=3, concurrency=1
    )
    argv_serial = serial._build_argv(
        task=task,
        candidate={},
        jobs_dir=tmp_path / "jobs2",
        job_name="j",
    )
    assert argv_serial[argv_serial.index("-n") + 1] == "1"
