"""Self-select base policy: default-base choice + manifest/matrix artifacts."""

import json

from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.schemas import CandidateResult


def _candidate(run_dir, cid, passrate, average_score, breakdown):
    result_path = run_dir / "candidate_results" / f"{cid}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps({"candidate": {}, "tasks": [], "score_breakdown": breakdown}),
        encoding="utf-8",
    )
    return CandidateResult.from_dict(
        {
            "candidate_id": cid,
            "scaffold_name": "s",
            "passrate": passrate,
            "average_score": average_score,
            "token_consuming": 0,
            "count": 2,
            "avg_token_consuming": 0.0,
            "avg_prompt_tokens": 0.0,
            "avg_completion_tokens": 0.0,
            "config": {"name": cid, "hypothesis": "test hypothesis line\nmore"},
            "result_path": str(result_path),
        }
    )


def _make_optimizer(tmp_path):
    cfg = OptimizerConfig(run_id="smoke", out_dir=tmp_path / "run", iterations=1)
    return LocomoOptimizer(cfg)


def _seed_candidates(tmp_path):
    run_dir = tmp_path / "run"
    seed = _candidate(
        run_dir, "seed_scaffold", 0.3, 0.40,
        {"all": {"average_score": 0.4}, "t1": {"average_score": 0.3}, "t2": {"average_score": 0.5}},
    )
    c1 = _candidate(
        run_dir, "iter001_a", 0.6, 0.44,
        {"all": {"average_score": 0.44}, "t1": {"average_score": 0.4}, "t2": {"average_score": 0.48}},
    )
    c2 = _candidate(
        run_dir, "iter002_b", 0.6, 0.52,
        {"all": {"average_score": 0.52}, "t1": {"average_score": 0.5}, "t2": {"average_score": 0.54}},
    )
    # Best average_score of the run, but its snapshot is NOT on disk below, so
    # it must never be picked as the default base.
    c3 = _candidate(
        run_dir, "iter003_c", 0.5, 0.60,
        {"all": {"average_score": 0.6}, "t1": {"average_score": 0.62}, "t2": {"average_score": 0.58}},
    )
    for i in (1, 2):
        snapshot = (
            run_dir / "proposer_calls" / f"iter_{i:03d}"
            / "source_snapshot" / "candidate" / "project_source"
        )
        snapshot.mkdir(parents=True)
    return [seed, c1, c2, c3]


def test_self_select_default_base_is_lex_best_with_snapshot(tmp_path):
    opt = _make_optimizer(tmp_path)
    candidates = _seed_candidates(tmp_path)
    # iters 1 and 2 tie on passrate 0.6 -> average_score tiebreak picks 2;
    # iter 3 has the highest average_score but a lower passrate and no snapshot.
    assert opt._self_select_default_base(candidates, iteration=4) == 2


def test_self_select_default_base_none_when_nothing_beats_seed(tmp_path):
    opt = _make_optimizer(tmp_path)
    run_dir = tmp_path / "run"
    seed = _candidate(run_dir, "seed_scaffold", 0.5, 0.5, {"all": {"average_score": 0.5}})
    weak = _candidate(run_dir, "iter001_weak", 0.4, 0.6, {"all": {"average_score": 0.6}})
    snapshot = (
        run_dir / "proposer_calls" / "iter_001"
        / "source_snapshot" / "candidate" / "project_source"
    )
    snapshot.mkdir(parents=True)
    assert opt._self_select_default_base([seed, weak], iteration=2) is None


def test_self_select_manifest_and_matrix(tmp_path):
    opt = _make_optimizer(tmp_path)
    candidates = _seed_candidates(tmp_path)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    opt._write_self_select_manifest(
        workspace,
        candidates,
        iteration=4,
        default_base_iter=2,
        reference_iterations=(1, 2, 3),
    )

    manifest = json.loads((workspace / "frontier_manifest.json").read_text())
    assert manifest["default_base_iter"] == 2
    rows = {row["iteration"]: row for row in manifest["candidates"]}
    assert rows[2]["is_default_base"] and not rows[1]["is_default_base"]
    assert rows[2]["source_snapshot"] == "reference_iterations/iter_002/source_snapshot"
    assert rows[1]["hypothesis"] == "test hypothesis line"

    matrix = json.loads((workspace / "task_score_matrix.json").read_text())
    # Full history per task, one column per iteration — never a per-task max.
    assert matrix["tasks"]["t1"] == {
        "iter_000": 0.3,
        "iter_001": 0.4,
        "iter_002": 0.5,
        "iter_003": 0.62,
    }
    assert "all" not in matrix["tasks"]
