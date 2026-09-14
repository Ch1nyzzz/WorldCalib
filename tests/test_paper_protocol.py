"""Behavioral regressions for the paper protocol and release entry points."""

from pathlib import Path
from types import SimpleNamespace
from importlib import import_module
import pytest

from worldcalib.optimize_cli import BENCHMARKS, build_parser, _common_config
from worldcalib.optimizer import LocomoOptimizer
from worldcalib.prompts import load_proposer_skill
from worldcalib.world_model import EMPTY_WORLD_MODEL


def optimizer(tmp_path, target="agent", variant="calib", limit=0):
    obj = object.__new__(LocomoOptimizer)
    obj.run_dir = tmp_path
    obj.config = SimpleNamespace(progressive_target_system=target,
        proposer_variant=variant, test_frontier_candidate_limit=limit)
    return obj


def candidate(cid, score):
    return SimpleNamespace(candidate_id=cid, passrate=score, scaffold_name="seed",
        token_consuming=0, avg_token_consuming=0, average_score=score,
        result_path="", config={})


def test_agent_heldout_uses_earliest_tie_before_frontier_truncation(tmp_path):
    obj = optimizer(tmp_path)
    rows = [candidate(f"iter{i:03d}_seed", .8) for i in (7, 6, 5, 1)]
    assert [c.candidate_id for c in obj._heldout_candidates(rows)] == ["iter001_seed"]
    assert obj._heldout_candidates([]) == []


def test_memory_heldout_preserves_top_three_and_override(tmp_path):
    rows = [candidate(f"iter{i:03d}_seed", i / 10) for i in range(5)]
    obj = optimizer(tmp_path, target="memgpt")
    assert [c.passrate for c in obj._heldout_candidates(rows)] == [.4, .3, .2]
    obj.config.test_frontier_candidate_limit = 1
    assert len(obj._heldout_candidates(rows)) == 1


@pytest.mark.parametrize("variant", ["calib", "nowmc"])
def test_workspace_stages_only_paper_calibration_files(tmp_path, variant):
    obj = optimizer(tmp_path, variant=variant)
    (tmp_path / "world_model_calibration.md").write_text(EMPTY_WORLD_MODEL)
    (tmp_path / "seed_task_table.json").write_text("{}")
    prev = obj._iteration_dir(1)
    (prev / "workspace").mkdir(parents=True)
    (prev / "workspace/prediction.md").write_text("previous prediction")
    (prev / "aggregate_grade.md").write_text("old extended grade")
    workspace = tmp_path / "new_workspace"
    workspace.mkdir()
    obj._sync_calibration_into_workspace(workspace, 2)
    expected = {"world_model_calibration.md", "prev_prediction.md"} if variant == "calib" else set()
    assert {p.name for p in workspace.iterdir()} == expected


def test_history_preserved_when_proposer_rewrites_it(tmp_path):
    obj = optimizer(tmp_path)
    (tmp_path / "world_model_calibration.md").write_text("old head\n## iter_000 -> iter_001\nold evidence\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "world_model_calibration.md").write_text("new head\n## iter_001 -> iter_002\nnew evidence\n")
    obj._sync_calibration_back_from_workspace(workspace)
    result = (tmp_path / "world_model_calibration.md").read_text()
    assert result.startswith("new head")
    assert "old evidence" in result and "new evidence" in result


@pytest.mark.parametrize("benchmark", BENCHMARKS)
def test_benchmark_optimizer_imports(benchmark):
    paths = {"locomo": "memory.locomo_optimizer", "longmemeval": "memory.longmemeval_optimizer", "tb2": "tb2.tb2_optimizer"}
    import_module("worldcalib.benchmarks." + paths.get(benchmark, benchmark + ".optimizer"))


@pytest.mark.parametrize("benchmark", BENCHMARKS)
def test_no_extension_in_resolved_calibration_skills(benchmark):
    text = load_proposer_skill(benchmark + "_calib")
    for token in ("## Task map", "## Residual", "seed_task_table.json", "prev_aggregate_grade.md", "predictions_history/", "Aggregate bet (machine)"):
        assert token not in text
    assert "predict → observe → correct" in text
    assert "<!-- INCLUDE:" not in text


def test_kimi_endpoint_and_key_are_paired(monkeypatch, tmp_path):
    monkeypatch.setenv("KIMI_API_KEY", "test-key")
    monkeypatch.setenv("KIMI_BASE_URL", "https://example.invalid/anthropic")
    args = build_parser().parse_args(["gaia", "--run-id", "test"])
    cfg = _common_config(args, tmp_path, tmp_path / "run")
    assert cfg["claude_auth_token"] == "test-key"
    assert cfg["claude_base_url"] == "https://example.invalid/anthropic"
    args.proposer_auth_token = "override"
    args.proposer_base_url = "https://override.invalid/anthropic"
    cfg = _common_config(args, tmp_path, tmp_path / "run")
    assert cfg["claude_auth_token"] == "override"
    assert cfg["claude_base_url"] == args.proposer_base_url


def test_missing_kimi_config_fails_early(monkeypatch, tmp_path):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_BASE_URL", raising=False)
    args = build_parser().parse_args(["gaia", "--run-id", "test"])
    with pytest.raises(ValueError, match="Kimi proposer requires"):
        _common_config(args, tmp_path, tmp_path / "run")
