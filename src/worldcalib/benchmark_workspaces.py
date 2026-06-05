"""Benchmark-scoped source workspaces for proposer optimization."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


MINIMAL_BENCHMARK_PACKAGE_INIT = (
    '"""Benchmark-scoped candidate package."""\n\n'
    "__all__: list[str] = []\n"
)


@dataclass(frozen=True)
class BenchmarkWorkspaceSpec:
    """Source files that define one benchmark's editable proposer workspace."""

    benchmark: str
    source_files: tuple[str, ...]
    primary_source_file: str

    @property
    def allowed_memomemo_modules(self) -> tuple[str, ...]:
        """Top-level worldcalib modules candidates may import from this snapshot."""

        modules: set[str] = set()
        for rel in self.source_files:
            parts = Path(rel).parts
            if not parts:
                continue
            top = parts[0]
            if top == "__init__.py":
                continue
            if top.endswith(".py"):
                modules.add(top.removesuffix(".py"))
            else:
                modules.add(top)
        return tuple(sorted(modules))


LOCOMO_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="locomo",
    primary_source_file="scaffolds/base.py",
    source_files=(
        "__init__.py",
        "dynamic.py",
        "metrics.py",
        "model.py",
        "schemas.py",
        "source_base.py",
        "upstream.py",
        "scaffolds/__init__.py",
        "scaffolds/base.py",
        "memory/__init__.py",
        "memory/locomo.py",
        "memory/scaffolds/__init__.py",
        "memory/scaffolds/bm25_scaffold.py",
        "memory/scaffolds/memgpt_scaffold.py",
        "utils/__init__.py",
        "utils/text.py",
    ),
)


LONGMEMEVAL_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="longmemeval",
    primary_source_file="scaffolds/base.py",
    source_files=(
        *LOCOMO_WORKSPACE_SPEC.source_files,
        "memory/longmemeval.py",
    ),
)


AGENTBENCH_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="agentbench",
    primary_source_file="agentic/backends/agentbench/seed_passthrough.py",
    source_files=(
        *LOCOMO_WORKSPACE_SPEC.source_files,
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "agentic/__init__.py",
        "agentic/backends/__init__.py",
        "agentic/backends/agentbench/__init__.py",
        "agentic/backends/agentbench/base.py",
        "agentic/backends/agentbench/seed_passthrough.py",
    ),
)

TAU2_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="tau2",
    primary_source_file="agentic/backends/tau2/seed_passthrough.py",
    source_files=(
        *LOCOMO_WORKSPACE_SPEC.source_files,
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "agentic/__init__.py",
        "agentic/backends/__init__.py",
        "agentic/backends/tau2/__init__.py",
        "agentic/backends/tau2/base.py",
        "agentic/backends/tau2/seed_passthrough.py",
    ),
)


ARC_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="arc_agi2",
    primary_source_file="reasoning/arc_scaffolds/seed_passthrough.py",
    source_files=(
        *LOCOMO_WORKSPACE_SPEC.source_files,
        "optcore/__init__.py",
        "optcore/scaffold_base.py",
        "reasoning/__init__.py",
        "reasoning/arc_scaffolds/__init__.py",
        "reasoning/arc_scaffolds/base.py",
        "reasoning/arc_scaffolds/seed_passthrough.py",
    ),
)


SWEBENCH_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="swebench",
    primary_source_file="coding/swebench.py",
    source_files=(
        "__init__.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "coding/__init__.py",
        "coding/swebench.py",
        "coding/swebench_optimizer.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
    ),
)


TERMINUS_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="terminus",
    primary_source_file="terminus.py",
    source_files=(
        "__init__.py",
        "benchmark_tasks.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
        "terminus.py",
        "terminus_optimizer.py",
    ),
)


GRAPH_COLOURING_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="graph_colouring",
    primary_source_file="graph_colouring.py",
    source_files=(
        "__init__.py",
        "benchmark_tasks.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "graph_colouring.py",
        "graph_colouring_optimizer.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
    ),
)


def copy_benchmark_project_source(
    *,
    project_root: Path,
    dest_pkg: Path,
    spec: BenchmarkWorkspaceSpec,
) -> tuple[str, ...]:
    """Copy exactly the source files declared by a benchmark workspace spec."""

    source_pkg = project_root / "src" / "worldcalib"
    copied: list[str] = []
    for rel in spec.source_files:
        src = source_pkg / rel
        if not src.exists():
            raise FileNotFoundError(f"benchmark source file does not exist: {src}")
        dest = dest_pkg / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Path(rel).parts == ("__init__.py",):
            dest.write_text(MINIMAL_BENCHMARK_PACKAGE_INIT, encoding="utf-8")
        else:
            shutil.copy2(src, dest)
        copied.append(rel)
    return tuple(copied)
