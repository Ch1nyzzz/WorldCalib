"""Release-boundary checks for the paper-aligned public package."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

import pytest

from worldcalib.benchmark_workspaces import (
    APPWORLD_WORKSPACE_SPEC,
    GAIA_WORKSPACE_SPEC,
    LOCOMO_WORKSPACE_SPEC,
    LONGMEMEVAL_WORKSPACE_SPEC,
    SPIDER2_WORKSPACE_SPEC,
    TB2_WORKSPACE_SPEC,
    TOOLATHLON_WORKSPACE_SPEC,
)
from worldcalib.benchmarks.appworld.data import load_split_ids
from worldcalib.benchmarks.gaia.optimizer import GaiaOptimizerConfig
from worldcalib.benchmarks.spider2.data import load_split as load_spider2_split
from worldcalib.benchmarks.tb2.data import load_split as load_tb2_split
from worldcalib.benchmarks.toolathlon.data import load_split as load_toolathlon_split
from worldcalib.optimize_cli import BENCHMARKS, build_parser
from worldcalib.prompts import load_proposer_skill
from worldcalib.world_model import EMPTY_WORLD_MODEL


PAPER_BENCHMARKS = (
    "longmemeval",
    "locomo",
    "gaia",
    "appworld",
    "tb2",
    "toolathlon",
    "spider2",
)

WORKSPACE_SPECS = (
    LONGMEMEVAL_WORKSPACE_SPEC,
    LOCOMO_WORKSPACE_SPEC,
    GAIA_WORKSPACE_SPEC,
    APPWORLD_WORKSPACE_SPEC,
    TB2_WORKSPACE_SPEC,
    TOOLATHLON_WORKSPACE_SPEC,
    SPIDER2_WORKSPACE_SPEC,
)


def test_cli_exposes_only_paper_release_scope() -> None:
    assert BENCHMARKS == PAPER_BENCHMARKS


@pytest.mark.parametrize("benchmark", ("webshop", "os", "agentbench", "tau2", "arc_agi2", "swebench", "autolab", "alfworld", "db"))
def test_cli_rejects_explicitly_excluded_benchmarks(benchmark: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([benchmark, "--run-id", "boundary-test"])


def test_packaged_splits_match_paper_counts_and_are_disjoint() -> None:
    appworld_train = load_split_ids("train")
    appworld_test = load_split_ids("test")
    assert (len(appworld_train), len(appworld_test)) == (45, 372)
    assert set(appworld_train).isdisjoint(appworld_test)

    spider2 = load_spider2_split()
    assert (len(spider2["train"]), len(spider2["test"])) == (31, 104)
    assert set(spider2["train"]).isdisjoint(spider2["test"])

    tb2 = load_tb2_split()
    assert (len(tb2["train"]), len(tb2["test"])) == (20, 67)
    assert set(tb2["train"]).isdisjoint(tb2["test"])

    toolathlon = load_toolathlon_split()
    assert (
        len(toolathlon["train"]),
        len(toolathlon["test"]),
        len(toolathlon["excluded"]),
    ) == (36, 64, 8)
    assert len(
        {
            *toolathlon["train"],
            *toolathlon["test"],
            *toolathlon["excluded"],
        }
    ) == 108


def test_gaia_library_defaults_match_the_paper_split() -> None:
    config = GaiaOptimizerConfig(run_id="release-boundary", out_dir=Path("runs/release-boundary"))
    assert (config.gaia_train_size, config.gaia_test_size) == (40, 99)


def test_empty_world_model_matches_calibration_contract() -> None:
    for heading in (
        "## Beliefs",
        "## Experiments",
        "## Calibration",
    ):
        assert heading in EMPTY_WORLD_MODEL


def test_all_release_prompts_resolve_without_removed_service_contract() -> None:
    removed_service = "".join(("run", "store"))
    for benchmark in PAPER_BENCHMARKS:
        for variant in ("calib", "nowmc"):
            prompt = load_proposer_skill(f"{benchmark}_{variant}")
            assert prompt.strip()
            normalized = re.sub(r"[\s_-]+", "", prompt.lower())
            assert removed_service not in normalized


def test_benchmark_workspace_resources_are_complete() -> None:
    package_root = files("worldcalib")
    for spec in WORKSPACE_SPECS:
        assert spec.primary_source_file in spec.source_files
        for relative in spec.source_files:
            resource = package_root.joinpath(*Path(relative).parts)
            assert resource.is_file(), f"{spec.benchmark}: missing {relative}"


def test_source_has_no_private_paths_or_source_tree_inference() -> None:
    package_root = Path(str(files("worldcalib")))
    personal_path = re.compile(r"/(?:data/)?home/[^/\s\"']+")
    source_tree_inference = re.compile(
        r"(?:Path\s*\(\s*__file__\s*\)|__file__).*?\.parents?(?:\[|\b)"
    )
    removed_service = "".join(("run", "store"))

    violations: list[str] = []
    for path in sorted(package_root.rglob("*")):
        if path.suffix not in {".py", ".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        normalized = re.sub(r"[\s_-]+", "", text.lower())
        if removed_service in normalized:
            violations.append(f"{path}: removed service reference")
        if personal_path.search(text):
            violations.append(f"{path}: personal absolute path")
        if source_tree_inference.search(text):
            violations.append(f"{path}: source-tree path inference")
    assert not violations, "\n".join(violations)


def test_removed_benchmark_packages_are_absent() -> None:
    benchmark_root = files("worldcalib.benchmarks")
    for name in ("agentbench", "autolab", "coding", "reasoning"):
        assert not benchmark_root.joinpath(name).is_dir()
    removed_module = "_".join(("run", "store")) + ".py"
    assert not files("worldcalib").joinpath(removed_module).is_file()
