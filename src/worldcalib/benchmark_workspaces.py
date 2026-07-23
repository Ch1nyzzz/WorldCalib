"""Benchmark-scoped source snapshots for proposer optimization."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path


MINIMAL_PACKAGE_INIT = (
    '"""Benchmark-scoped candidate package."""\n\n'
    "__all__: list[str] = []\n"
)


@dataclass(frozen=True)
class BenchmarkWorkspaceSpec:
    """Files that define one benchmark's editable proposer workspace."""

    benchmark: str
    source_files: tuple[str, ...]
    primary_source_file: str

    @property
    def allowed_memomemo_modules(self) -> tuple[str, ...]:
        modules: set[str] = set()
        for rel in self.source_files:
            parts = Path(rel).parts
            if not parts or parts[0] == "__init__.py":
                continue
            modules.add(
                parts[0].removesuffix(".py")
                if parts[0].endswith(".py")
                else parts[0]
            )
        return tuple(sorted(modules))


_MEMORY_SOURCE_FILES = (
    "__init__.py",
    "dynamic.py",
    "metrics.py",
    "model.py",
    "schemas.py",
    "source_base.py",
    "upstream.py",
    "scaffolds/__init__.py",
    "scaffolds/base.py",
    "benchmarks/__init__.py",
    "benchmarks/memory/__init__.py",
    "benchmarks/memory/locomo.py",
    "benchmarks/memory/scaffolds/__init__.py",
    "benchmarks/memory/scaffolds/bm25_scaffold.py",
    "benchmarks/memory/scaffolds/memgpt_scaffold.py",
    "utils/__init__.py",
    "utils/text.py",
)


LOCOMO_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="locomo",
    primary_source_file="scaffolds/base.py",
    source_files=_MEMORY_SOURCE_FILES,
)


LONGMEMEVAL_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="longmemeval",
    primary_source_file="scaffolds/base.py",
    source_files=(*_MEMORY_SOURCE_FILES, "benchmarks/memory/longmemeval.py"),
)


GAIA_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="gaia",
    primary_source_file="benchmarks/gaia/seed_passthrough.py",
    source_files=(
        *_MEMORY_SOURCE_FILES,
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "benchmarks/gaia/__init__.py",
        "benchmarks/gaia/base.py",
        "benchmarks/gaia/seed_passthrough.py",
        "benchmarks/gaia/llm.py",
        "benchmarks/gaia/tools/__init__.py",
        "benchmarks/gaia/tools/file_read.py",
        "benchmarks/gaia/tools/url_fetch.py",
        "benchmarks/gaia/tools/web_search.py",
        "benchmarks/gaia/tools/python_exec.py",
    ),
)


SPIDER2_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="spider2",
    primary_source_file="benchmarks/spider2/seed_passthrough.py",
    source_files=(
        *_MEMORY_SOURCE_FILES,
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "benchmarks/spider2/__init__.py",
        "benchmarks/spider2/base.py",
        "benchmarks/spider2/seed_passthrough.py",
        "benchmarks/spider2/llm.py",
    ),
)


TOOLATHLON_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="toolathlon",
    primary_source_file="benchmarks/toolathlon/runner.py",
    source_files=(
        "__init__.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "benchmarks/__init__.py",
        "benchmarks/toolathlon/__init__.py",
        "benchmarks/toolathlon/data.py",
        "benchmarks/toolathlon/runner.py",
        "benchmarks/toolathlon/optimizer.py",
    ),
)


APPWORLD_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="appworld",
    primary_source_file="benchmarks/appworld/runner.py",
    source_files=(
        "__init__.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "benchmarks/__init__.py",
        "benchmarks/appworld/__init__.py",
        "benchmarks/appworld/data.py",
        "benchmarks/appworld/runner.py",
        "benchmarks/appworld/optimizer.py",
    ),
)


TB2_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="tb2",
    primary_source_file="benchmarks/tb2/tb2.py",
    source_files=(
        "__init__.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
        "benchmarks/__init__.py",
        "benchmarks/tb2/__init__.py",
        "benchmarks/tb2/data.py",
        "benchmarks/tb2/tb2.py",
        "benchmarks/tb2/tb2_optimizer.py",
        "runners/__init__.py",
        "runners/harbor.py",
    ),
)


def package_source_root() -> Traversable:
    """Return the installed worldcalib package through importlib.resources."""

    return files("worldcalib")


def copy_benchmark_project_source(
    *,
    dest_pkg: Path,
    spec: BenchmarkWorkspaceSpec,
    source_pkg: Traversable | None = None,
) -> tuple[str, ...]:
    """Copy exactly the package resources declared by a workspace spec."""

    root = source_pkg or package_source_root()
    copied: list[str] = []
    for rel in spec.source_files:
        src = root.joinpath(*Path(rel).parts)
        if not src.is_file():
            raise FileNotFoundError(f"benchmark package resource is missing: {rel}")
        dest = dest_pkg / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Path(rel).parts == ("__init__.py",):
            dest.write_text(MINIMAL_PACKAGE_INIT, encoding="utf-8")
        else:
            with src.open("rb") as source_handle, dest.open("wb") as dest_handle:
                shutil.copyfileobj(source_handle, dest_handle)
        copied.append(rel)
    return tuple(copied)
