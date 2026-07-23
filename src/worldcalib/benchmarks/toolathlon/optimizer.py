"""Toolathlon optimization entry point (containerized external-runner backend).

This external-process backend overrides
``_evaluate_proposed`` to drive a per-candidate external runner
(ToolathlonSourceRunner) instead of the base in-process scaffold path. The
proposer-edited agent source travels via ``source_project_path`` (the snapshot's
upstream_source/toolathlon), and the runner overlays it onto a working tree
before invoking Toolathlon's own run_parallel.py scheduler.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.benchmark_workspaces import (
    BenchmarkWorkspaceSpec,
    TOOLATHLON_WORKSPACE_SPEC,
)
from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.paths import resolve_external_path
from worldcalib.schemas import CandidateResult

from worldcalib.benchmarks.toolathlon.data import (
    TASKS_SUBDIR,
    ToolathlonTask,
    load_toolathlon_tasks,
)
from worldcalib.benchmarks.toolathlon.runner import (
    AGENT_PROMPT_REL,
    DEFAULT_MAXSTEP,
    DEFAULT_PER_TASK_TIMEOUT_S,
    DEFAULT_TOOLATHLON_AGENT_NAME,
    ToolathlonSourceRunner,
    run_toolathlon_frontier,
)


@dataclass(frozen=True)
class ToolathlonOptimizerConfig(OptimizerConfig):
    """Configuration for source-backed Toolathlon agent optimization."""

    toolathlon_root: Path | None = None
    toolathlon_concurrency: int = 8
    toolathlon_maxstep: int = DEFAULT_MAXSTEP
    toolathlon_per_task_timeout_s: int = DEFAULT_PER_TASK_TIMEOUT_S
    force: bool = False
    scaffolds: tuple[str, ...] = (DEFAULT_TOOLATHLON_AGENT_NAME,)
    progressive_target_system: str = DEFAULT_TOOLATHLON_AGENT_NAME


class ToolathlonOptimizer(LocomoOptimizer):
    """Proposer loop for containerized Toolathlon agent candidates."""

    workspace_spec: BenchmarkWorkspaceSpec = TOOLATHLON_WORKSPACE_SPEC
    config: ToolathlonOptimizerConfig

    def __init__(self, config: ToolathlonOptimizerConfig) -> None:
        super().__init__(config)
        self._toolathlon_root = resolve_external_path(
            config.toolathlon_root,
            env_var="TOOLATHLON_ROOT",
            label="Toolathlon checkout",
        )

    # ---- examples / seed --------------------------------------------------

    def _load_examples(self) -> list[ToolathlonTask]:
        return load_toolathlon_tasks(self.config.split, limit=self.config.limit)

    def _make_runner(self, tasks: list[ToolathlonTask], out_dir: Path) -> ToolathlonSourceRunner:
        return ToolathlonSourceRunner(
            tasks=tasks,
            out_dir=out_dir,
            toolathlon_root=self._toolathlon_root,
            model=self.config.model,
            concurrency=self.config.toolathlon_concurrency,
            maxstep=self.config.toolathlon_maxstep,
            per_task_timeout_s=self.config.toolathlon_per_task_timeout_s,
            dry_run=self.config.dry_run,
            force=self.config.force,
        )

    def _run_seed_frontier(self) -> dict[str, Any]:
        return run_toolathlon_frontier(
            out_dir=self.run_dir,
            split=self.config.split,
            limit=self.config.limit,
            model=self.config.model,
            concurrency=self.config.toolathlon_concurrency,
            maxstep=self.config.toolathlon_maxstep,
            per_task_timeout_s=self.config.toolathlon_per_task_timeout_s,
            dry_run=self.config.dry_run,
            force=self.config.force,
            pareto_quality_threshold=self.config.pareto_quality_threshold,
            toolathlon_root=self._toolathlon_root,
        )

    def _benchmark_prompt_name(self) -> str:
        return "Toolathlon multi-app tool-use task completion"

    def _raw_data_policy_name(self) -> str:
        return "Toolathlon task gold end-states and evaluator checks"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "toolathlon",
            "kind": "toolathlon_agent",
            "scoring_method": "end_state",
        }

    # ---- evaluation (external runner) ------------------------------------

    def _evaluate_proposed(
        self,
        iteration: int,
        proposed: list[dict[str, Any]],
        examples: list[ToolathlonTask],
    ) -> list[CandidateResult]:
        runner = self._make_runner(examples, out_dir=self.run_dir)
        results: list[CandidateResult] = []
        for raw in proposed:
            if not isinstance(raw, dict):
                continue
            candidate = dict(raw)
            agent_name = str(
                candidate.get("agent_name")
                or candidate.get("scaffold_name")
                or DEFAULT_TOOLATHLON_AGENT_NAME
            )
            candidate.setdefault("agent_name", agent_name)
            candidate.setdefault("source_family", DEFAULT_TOOLATHLON_AGENT_NAME)
            self._normalize_candidate_source_project_path(candidate)

            violations = self._candidate_code_policy_violations(candidate)
            if violations:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_policy_rejected",
                        "candidate": candidate,
                        "violations": violations,
                    }
                )
                continue

            candidate_name = str(candidate.get("name") or agent_name)
            candidate_id = f"iter{iteration:03d}_{candidate_name}"
            try:
                result = runner.evaluate_candidate(
                    candidate=candidate,
                    candidate_id=candidate_id,
                    agent_name=agent_name,
                )
            except Exception as exc:  # noqa: BLE001 - log and continue
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_eval_failed",
                        "candidate": candidate,
                        "candidate_id": candidate_id,
                        "error": str(exc),
                    }
                )
                continue
            results.append(result)
            self._append_summary(iteration=iteration, candidate=result, proposal=candidate)
        return results

    def _run_test_frontier(self, candidates: list[CandidateResult]) -> dict[str, Any]:
        full_frontier = self._quality_frontier(candidates)
        candidate_limit = max(0, int(self.config.test_frontier_candidate_limit or 0))
        frontier = full_frontier[:candidate_limit] if candidate_limit else full_frontier
        test_dir = self.run_dir / "test_frontier"
        specs_dir = test_dir / "candidate_specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        examples = load_toolathlon_tasks(self.config.test_split, limit=self.config.test_limit)
        runner = self._make_runner(examples, out_dir=test_dir)

        rows: list[dict[str, Any]] = []
        test_results: list[CandidateResult] = []
        failures: list[dict[str, Any]] = []
        for candidate in frontier:
            spec = self._toolathlon_test_spec(candidate)
            spec_path = specs_dir / f"{spec['candidate_id']}.json"
            spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                result = runner.evaluate_candidate(
                    candidate=spec,
                    candidate_id=str(spec["candidate_id"]),
                    agent_name=str(spec.get("agent_name") or DEFAULT_TOOLATHLON_AGENT_NAME),
                )
            except Exception as exc:  # noqa: BLE001 - keep testing the rest
                failure = {
                    "original_candidate_id": candidate.candidate_id,
                    "test_candidate_id": spec["candidate_id"],
                    "candidate_spec_path": str(spec_path),
                    "error": str(exc),
                }
                failures.append(failure)
                rows.append(
                    {
                        "original_candidate": candidate.to_dict(),
                        "candidate_spec_path": str(spec_path),
                        "error": str(exc),
                    }
                )
                self._append_event({"event": "test_frontier_candidate_failed", **failure})
                continue
            test_results.append(result)
            rows.append(
                {
                    "original_candidate": candidate.to_dict(),
                    "candidate_spec_path": str(spec_path),
                    "test_candidate": result.to_dict(),
                }
            )

        (test_dir / "test_results.json").write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        test_frontier_path = test_dir / "test_pareto_frontier.json"
        save_frontier(
            test_frontier_path,
            [
                ParetoPoint(
                    candidate_id=item.candidate_id,
                    scaffold_name=item.scaffold_name,
                    passrate=item.passrate,
                    token_consuming=item.token_consuming,
                    avg_token_consuming=item.avg_token_consuming,
                    average_score=item.average_score,
                    result_path=item.result_path,
                    config=item.config,
                )
                for item in test_results
            ],
            quality_gap_threshold=self.config.pareto_quality_threshold,
        )
        summary = {
            "benchmark": "toolathlon",
            "split": self.config.test_split,
            "limit": self.config.test_limit,
            "count": len(examples),
            "train_frontier_total_count": len(full_frontier),
            "candidate_limit": candidate_limit,
            "train_frontier_count": len(frontier),
            "evaluated_count": len(test_results),
            "failed_count": len(failures),
            "test_dir": str(test_dir),
            "failures": failures,
        }
        summary_path = self.run_dir / "test_frontier_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["summary_path"] = str(summary_path)
        return summary

    def _toolathlon_test_spec(self, candidate: CandidateResult) -> dict[str, Any]:
        config = dict(candidate.config) if isinstance(candidate.config, dict) else {}
        extra = config.get("extra") if isinstance(config.get("extra"), dict) else {}
        spec = dict(config)
        spec["candidate_id"] = self._test_candidate_id(candidate.candidate_id)
        spec["original_candidate_id"] = candidate.candidate_id
        spec["agent_name"] = str(
            spec.get("agent_name")
            or spec.get("scaffold_name")
            or candidate.scaffold_name
            or DEFAULT_TOOLATHLON_AGENT_NAME
        )
        spec["scaffold_name"] = DEFAULT_TOOLATHLON_AGENT_NAME
        spec["source_family"] = DEFAULT_TOOLATHLON_AGENT_NAME
        if "name" not in spec:
            spec["name"] = candidate.scaffold_name or DEFAULT_TOOLATHLON_AGENT_NAME
        if "source_project_path" not in spec and extra.get("source_project_path"):
            spec["source_project_path"] = str(extra["source_project_path"])
        return spec

    # ---- source snapshot (editable Toolathlon agent subset) --------------

    def _normalize_candidate_source_project_path(self, candidate: dict[str, Any]) -> None:
        """Keep a proposer-edited Toolathlon snapshot ahead of the default source."""

        extra = candidate.get("extra") if isinstance(candidate.get("extra"), dict) else {}
        if candidate.get("source_project_path"):
            return
        for key in ("source_project_path", "upstream_source_path", "toolathlon_source_path"):
            if extra.get(key):
                candidate["source_project_path"] = str(extra[key])
                return
        # None set -> baseline source (runner falls back to canonical files).

    def _copy_upstream_source_context(self, source_family: str, dest_dir: Path) -> None:
        super()._copy_upstream_source_context(source_family, dest_dir)
        if source_family != DEFAULT_TOOLATHLON_AGENT_NAME:
            return
        root = dest_dir / "upstream_source" / "toolathlon"
        root.mkdir(parents=True, exist_ok=True)
        # Snapshot the WHOLE editable agent source tree (utils/) — not a fixed
        # whitelist — so the proposer can edit existing modules AND add new
        # files/modules under it. Only utils/ (the agent implementation) is
        # editable; the run_parallel orchestration, scripts/, the per-task entry
        # and the evaluator stay canonical (off-limits) and are never snapshotted.
        utils_src = self._toolathlon_root / "utils"
        if utils_src.exists():
            shutil.copytree(
                utils_src,
                root / "utils",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                dirs_exist_ok=True,
            )
        # The shared agent-policy system prompt (one canonical template copy).
        prompt_src = self._representative_agent_prompt()
        if prompt_src is not None:
            shutil.copy2(prompt_src, root / AGENT_PROMPT_REL)
        (root / "EDITABLE.md").write_text(
            "\n".join(
                [
                    "# Toolathlon editable agent source",
                    "",
                    "Edit anything under here, then point `source_project_path` at",
                    "this dir (`source_snapshot/candidate/upstream_source/toolathlon`)",
                    "in pending_eval.json with kind=\"toolathlon_agent\".",
                    "",
                    "- `utils/**` — the ENTIRE agent implementation (the FC loop, history",
                    "  compaction, tool dispatch, conversation/MCP machinery, …). Edit any",
                    "  file AND add new files/modules — the whole tree propagates at eval.",
                    "- `agent_system_prompt.md` — shared agent policy prompt; the runner",
                    "  propagates it into every split task's docs/agent_system_prompt.md.",
                    "",
                    "Do NOT edit task user prompts, task docs, or the evaluator — those",
                    "define the task and the gold end-state and are not in this snapshot.",
                    "run_parallel.py / scripts/ / the per-task entry are eval orchestration",
                    "and are also not here — they stay canonical.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _representative_agent_prompt(self) -> Path | None:
        """Return one canonical agent_system_prompt.md (107/108 are identical)."""

        tasks_root = self._toolathlon_root / "tasks" / TASKS_SUBDIR
        if not tasks_root.is_dir():
            return None
        for task_dir in sorted(tasks_root.iterdir()):
            cand = task_dir / "docs" / "agent_system_prompt.md"
            if cand.is_file():
                return cand
        return None

    def _build_source_snapshot_workspace(
        self,
        *,
        iteration: int,
        source_family: str,
        call_dir: Path,
        target_system: str | None = None,
        snapshot_root: Path | None = None,
        generated_dir: Path | None = None,
        base_iter: int | None = None,
    ) -> Path:
        snapshot_root = super()._build_source_snapshot_workspace(
            iteration=iteration,
            source_family=source_family,
            call_dir=call_dir,
            target_system=target_system,
            snapshot_root=snapshot_root,
            generated_dir=generated_dir,
            base_iter=base_iter,
        )
        # CuraII lineage: when a parent base is supplied, replace the freshly
        # baseline-seeded upstream Toolathlon source with the parent iteration's
        # archived candidate source so the proposer edits on top of it.
        if base_iter is not None:
            candidate_dir = snapshot_root / "candidate"
            upstream = candidate_dir / "upstream_source" / "toolathlon"
            parent_upstream = (
                self._iteration_dir(base_iter)
                / "source_snapshot"
                / "candidate"
                / "upstream_source"
                / "toolathlon"
            )
            if parent_upstream.exists():
                if upstream.exists():
                    shutil.rmtree(upstream)
                shutil.copytree(
                    parent_upstream,
                    upstream,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        return snapshot_root
