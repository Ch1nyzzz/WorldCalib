"""Multi-run aggregation in prediction_feedback: stable-only outcomes,
per-run visibility, and mean per-task scores."""

import json

from worldcalib.prediction_feedback import (
    F2P,
    P2F,
    actual_flips,
    load_task_outcomes,
    load_task_pass_runs,
    load_task_scores,
)


def _write_result(tmp_path, tasks):
    p = tmp_path / "result.json"
    p.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    return p


def _row(tid, passed, score):
    return {"task_id": tid, "passed": passed, "score": score}


def test_single_run_unchanged(tmp_path):
    p = _write_result(
        tmp_path, [_row("t1", True, 1.0), _row("t2", False, 0.0)]
    )
    assert load_task_outcomes(p) == {"t1": True, "t2": False}
    assert load_task_scores(p) == {"t1": 1.0, "t2": 0.0}


def test_multirun_stable_tasks_kept(tmp_path):
    p = _write_result(
        tmp_path,
        [
            _row("t1", True, 1.0),
            _row("t1", True, 1.0),
            _row("t2", False, 0.0),
            _row("t2", False, 0.5),
        ],
    )
    assert load_task_outcomes(p) == {"t1": True, "t2": False}


def test_multirun_unstable_task_dropped(tmp_path):
    p = _write_result(
        tmp_path,
        [
            _row("t1", True, 1.0),
            _row("t1", False, 0.0),
            _row("t2", True, 1.0),
            _row("t2", True, 1.0),
        ],
    )
    out = load_task_outcomes(p)
    assert "t1" not in out
    assert out == {"t2": True}
    # the unstable task stays visible to callers that want to report it
    assert load_task_pass_runs(p)["t1"] == [True, False]


def test_multirun_scores_averaged(tmp_path):
    p = _write_result(
        tmp_path,
        [
            _row("t1", True, 1.0),
            _row("t1", False, 0.0),
            _row("t2", True, 0.8),
            _row("t2", True, 0.6),
        ],
    )
    scores = load_task_scores(p)
    assert scores["t1"] == 0.5
    assert abs(scores["t2"] - 0.7) < 1e-9


def test_passed_derived_from_score_when_missing(tmp_path):
    p = _write_result(
        tmp_path,
        [
            {"task_id": "t1", "score": 0.9},
            {"task_id": "t1", "score": 0.7},
            {"task_id": "t2", "score": 0.0},
            {"task_id": "t2", "score": 0.0},
        ],
    )
    assert load_task_outcomes(p) == {"t1": True, "t2": False}


def test_unstable_tasks_never_reach_flip_grading(tmp_path):
    base = _write_result(
        tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path / "b",
        [
            _row("stable_f2p", False, 0.0),
            _row("stable_f2p", False, 0.0),
            _row("stable_p2f", True, 1.0),
            _row("stable_p2f", True, 1.0),
            _row("unstable", True, 1.0),
            _row("unstable", False, 0.0),
        ],
    )
    (tmp_path / "c").mkdir()
    cand = _write_result(
        tmp_path / "c",
        [
            _row("stable_f2p", True, 1.0),
            _row("stable_f2p", True, 1.0),
            _row("stable_p2f", False, 0.0),
            _row("stable_p2f", False, 0.0),
            _row("unstable", False, 0.0),
            _row("unstable", False, 0.0),
        ],
    )
    flips = actual_flips(load_task_outcomes(cand), load_task_outcomes(base))
    assert flips == {"stable_f2p": F2P, "stable_p2f": P2F}
    assert "unstable" not in flips
