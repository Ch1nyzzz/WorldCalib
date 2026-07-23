"""Regression tests for two Harbor two-arm fixes.

Fix A: the optimizer persists the iter-0 seed frontier as a root
``run_summary.json`` so a sibling ablation arm can reuse the exact same baseline
via ``--baseline-dir`` (``load_baseline_candidates`` reads it, filtered by the
top-level split). Previously the optimizer wrote no root ``run_summary.json``,
so ``--baseline-dir <run>`` silently loaded zero candidates.

Fix B: ``HarborRunner`` now wires ``--harbor-concurrency`` into harbor's
``-n`` (concurrent trials). It used to be hardcoded to ``"1"``, so the flag was a
silent no-op and every task's ``n_attempts`` trials ran serially.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from worldcalib.runners.harbor import HarborRunner, HarborTask
from worldcalib.baseline import load_baseline_candidates
from worldcalib.optimizer import LocomoOptimizer
from worldcalib.schemas import CandidateResult


def _seed_candidate(count: int = 10) -> CandidateResult:
    return CandidateResult.from_dict(
        {
            "candidate_id": "iter000_terminus2_tb2",
            "scaffold_name": "terminus2_tb2",
            "count": count,
            "passrate": 0.0,
            "average_score": 0.4,
            "token_consuming": 0,
            "avg_token_consuming": 0,
            "avg_prompt_tokens": 0,
            "avg_completion_tokens": 0,
            "result_path": "",
            "config": {"name": "terminus2_tb2", "scaffold_name": "terminus2_tb2"},
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

    got = load_baseline_candidates(run_dir, split="train", scaffolds=["terminus2_tb2"])
    assert len(got) == 1
    assert int(got[0]["count"]) == 10
    assert got[0]["scaffold_name"] == "terminus2_tb2"

    # Split filter must reject a mismatched split.
    assert load_baseline_candidates(run_dir, split="test", scaffolds=["terminus2_tb2"]) == []


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
    """Fix B: -n reflects --harbor-concurrency instead of a hardcoded 1."""
    task = HarborTask(task_id="aes128_ctr", instruction="opt", path=tmp_path / "aes128_ctr")
    runner = HarborRunner(
        tasks=[task],
        out_dir=tmp_path / "out",
        n_attempts=3,
        concurrency=3,
    )
    argv = runner._build_argv(
        task=task,
        candidate={"model": "openai/deepseek-v4-flash"},
        jobs_dir=tmp_path / "jobs",
        job_name="terminus2_tb2__aes128_ctr",
    )
    # -k = attempts per trial, -n = concurrent trials.
    assert "-k" in argv and argv[argv.index("-k") + 1] == "3"
    assert "-n" in argv and argv[argv.index("-n") + 1] == "3"

    serial = HarborRunner(
        tasks=[task], out_dir=tmp_path / "out2", n_attempts=3, concurrency=1
    )
    argv_serial = serial._build_argv(
        task=task,
        candidate={},
        jobs_dir=tmp_path / "jobs2",
        job_name="j",
    )
    assert argv_serial[argv_serial.index("-n") + 1] == "1"


def test_max_turns_injected_unless_candidate_sets_it(tmp_path: Path) -> None:
    """max_turns=N adds --ak max_turns=N, but a candidate's own value wins."""
    task = HarborTask(task_id="t", instruction="x", path=tmp_path / "t")
    runner = HarborRunner(
        tasks=[task], out_dir=tmp_path / "o", n_attempts=3, max_turns=900
    )
    argv = runner._build_argv(task=task, candidate={}, jobs_dir=tmp_path / "j", job_name="j")
    assert "max_turns=900" in argv

    # Candidate-set max_turns is not overridden, and not duplicated.
    argv2 = runner._build_argv(
        task=task,
        candidate={"agent_kwargs": {"max_turns": 250}},
        jobs_dir=tmp_path / "j2",
        job_name="j",
    )
    assert "max_turns=250" in argv2 and "max_turns=900" not in argv2

    # No cap (default 0) -> no max_turns flag.
    plain = HarborRunner(tasks=[task], out_dir=tmp_path / "o3", n_attempts=3)
    argv3 = plain._build_argv(task=task, candidate={}, jobs_dir=tmp_path / "j3", job_name="j")
    assert not any(a.startswith("max_turns=") for a in argv3)


def test_max_task_seconds_caps_only_longer_tasks(tmp_path: Path) -> None:
    """Per-task --agent-timeout-multiplier shortens long tasks, leaves short ones."""
    short = HarborTask(task_id="short", instruction="x", path=tmp_path / "s", agent_timeout_sec=7200)
    long = HarborTask(task_id="long", instruction="x", path=tmp_path / "l", agent_timeout_sec=14400)
    runner = HarborRunner(
        tasks=[short, long],
        out_dir=tmp_path / "o",
        n_attempts=3,
        timeout_multiplier=1.0,
        max_task_seconds=10800,  # 180 min
    )

    def agent_mult(task):
        argv = runner._build_argv(task=task, candidate={}, jobs_dir=tmp_path / "j", job_name="j")
        return float(argv[argv.index("--agent-timeout-multiplier") + 1])

    # 7200s task is under the cap -> multiplier stays 1.0 (120 min).
    assert agent_mult(short) == 1.0
    # 14400s task is over the cap -> 10800/14400 = 0.75 (180 min).
    assert abs(agent_mult(long) - 0.75) < 1e-9

    # No cap -> no --agent-timeout-multiplier flag at all.
    plain = HarborRunner(tasks=[long], out_dir=tmp_path / "o2", n_attempts=3)
    argv = plain._build_argv(task=long, candidate={}, jobs_dir=tmp_path / "j2", job_name="j")
    assert "--agent-timeout-multiplier" not in argv
