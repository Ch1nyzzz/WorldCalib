"""AppWorld optimization entry point (external-runner backend).

Mirrors the toolathlon optimizer: an external-process backend that overrides
``_evaluate_proposed`` to drive a per-candidate :class:`AppWorldSourceRunner`
(subprocess eval in ``.venv-appworld``) instead of the base in-process scaffold
path. The proposer-edited agent travels via ``source_project_path`` (the
snapshot's ``upstream_source/appworld``); the runner passes that snapshot's
``agent.py`` to the eval subprocess.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.benchmark_workspaces import (
    APPWORLD_WORKSPACE_SPEC,
    BenchmarkWorkspaceSpec,
)
from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.paths import package_file
from worldcalib.schemas import CandidateResult, LocomoExample

from worldcalib.benchmarks.appworld.data import load_appworld_examples
from worldcalib.benchmarks.appworld.runner import (
    DEFAULT_APPWORLD_AGENT_NAME,
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_INTERACTIONS,
    DEFAULT_PER_TASK_TIMEOUT_S,
    AppWorldSourceRunner,
    run_appworld_frontier,
)


@dataclass(frozen=True)
class AppWorldOptimizerConfig(OptimizerConfig):
    """Configuration for source-backed AppWorld agent optimization."""

    appworld_concurrency: int = DEFAULT_CONCURRENCY
    appworld_max_interactions: int = DEFAULT_MAX_INTERACTIONS
    appworld_per_task_timeout_s: int = DEFAULT_PER_TASK_TIMEOUT_S
    appworld_repeats: int = 1  # k-times averaging per task (variance reduction)
    appworld_root: Path | None = None
    appworld_python: Path | None = None
    force: bool = False
    scaffolds: tuple[str, ...] = (DEFAULT_APPWORLD_AGENT_NAME,)
    progressive_target_system: str = DEFAULT_APPWORLD_AGENT_NAME


class AppWorldOptimizer(LocomoOptimizer):
    """Proposer loop for external-runner AppWorld code-agent candidates."""

    workspace_spec: BenchmarkWorkspaceSpec = APPWORLD_WORKSPACE_SPEC
    config: AppWorldOptimizerConfig

    def __init__(self, config: AppWorldOptimizerConfig) -> None:
        super().__init__(config)

    # ---- examples / seed --------------------------------------------------

    def _load_examples(self) -> list[LocomoExample]:
        return load_appworld_examples(self.config.split, limit=self.config.limit)

    def _make_runner(self, examples: list[LocomoExample], out_dir: Path) -> AppWorldSourceRunner:
        return AppWorldSourceRunner(
            examples=examples,
            out_dir=out_dir,
            model=self.config.model,
            concurrency=self.config.appworld_concurrency,
            max_interactions=self.config.appworld_max_interactions,
            per_task_timeout_s=self.config.appworld_per_task_timeout_s,
            repeats=self.config.appworld_repeats,
            appworld_root=self.config.appworld_root,
            appworld_python=self.config.appworld_python,
            work_dir=self.project_root,
            dry_run=self.config.dry_run,
            force=self.config.force,
        )

    def _run_seed_frontier(self) -> dict[str, Any]:
        return run_appworld_frontier(
            out_dir=self.run_dir,
            split=self.config.split,
            limit=self.config.limit,
            model=self.config.model,
            concurrency=self.config.appworld_concurrency,
            max_interactions=self.config.appworld_max_interactions,
            per_task_timeout_s=self.config.appworld_per_task_timeout_s,
            repeats=self.config.appworld_repeats,
            dry_run=self.config.dry_run,
            force=self.config.force,
            pareto_quality_threshold=self.config.pareto_quality_threshold,
            appworld_root=self.config.appworld_root,
            appworld_python=self.config.appworld_python,
            work_dir=self.project_root,
        )

    def _benchmark_prompt_name(self) -> str:
        return "AppWorld interactive coding agent (multi-app API tasks)"

    def _raw_data_policy_name(self) -> str:
        return "AppWorld task gold end-states and state-based unit tests"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "appworld",
            "kind": "appworld_agent",
            "scoring_method": "state_based",
        }

    # ---- evaluation (external runner) ------------------------------------

    def _evaluate_proposed(
        self,
        iteration: int,
        proposed: list[dict[str, Any]],
        examples: list[LocomoExample],
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
                or DEFAULT_APPWORLD_AGENT_NAME
            )
            candidate.setdefault("agent_name", agent_name)
            candidate.setdefault("source_family", DEFAULT_APPWORLD_AGENT_NAME)
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
        examples = load_appworld_examples(self.config.test_split, limit=self.config.test_limit)
        runner = self._make_runner(examples, out_dir=test_dir)

        rows: list[dict[str, Any]] = []
        test_results: list[CandidateResult] = []
        failures: list[dict[str, Any]] = []
        for candidate in frontier:
            spec = self._appworld_test_spec(candidate)
            spec_path = specs_dir / f"{spec['candidate_id']}.json"
            spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                result = runner.evaluate_candidate(
                    candidate=spec,
                    candidate_id=str(spec["candidate_id"]),
                    agent_name=str(spec.get("agent_name") or DEFAULT_APPWORLD_AGENT_NAME),
                )
            except Exception as exc:  # noqa: BLE001 - keep testing the rest
                failure = {
                    "original_candidate_id": candidate.candidate_id,
                    "test_candidate_id": spec["candidate_id"],
                    "candidate_spec_path": str(spec_path),
                    "error": str(exc),
                }
                failures.append(failure)
                rows.append({"original_candidate": candidate.to_dict(),
                             "candidate_spec_path": str(spec_path), "error": str(exc)})
                self._append_event({"event": "test_frontier_candidate_failed", **failure})
                continue
            test_results.append(result)
            rows.append({"original_candidate": candidate.to_dict(),
                         "candidate_spec_path": str(spec_path),
                         "test_candidate": result.to_dict()})

        (test_dir / "test_results.json").write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        save_frontier(
            test_dir / "test_pareto_frontier.json",
            [
                ParetoPoint(
                    candidate_id=item.candidate_id, scaffold_name=item.scaffold_name,
                    passrate=item.passrate, token_consuming=item.token_consuming,
                    avg_token_consuming=item.avg_token_consuming, average_score=item.average_score,
                    result_path=item.result_path, config=item.config,
                )
                for item in test_results
            ],
            quality_gap_threshold=self.config.pareto_quality_threshold,
        )
        summary = {
            "benchmark": "appworld",
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

    def _appworld_test_spec(self, candidate: CandidateResult) -> dict[str, Any]:
        config = dict(candidate.config) if isinstance(candidate.config, dict) else {}
        extra = config.get("extra") if isinstance(config.get("extra"), dict) else {}
        spec = dict(config)
        spec["candidate_id"] = self._test_candidate_id(candidate.candidate_id)
        spec["original_candidate_id"] = candidate.candidate_id
        spec["agent_name"] = str(
            spec.get("agent_name") or spec.get("scaffold_name")
            or candidate.scaffold_name or DEFAULT_APPWORLD_AGENT_NAME
        )
        spec["scaffold_name"] = DEFAULT_APPWORLD_AGENT_NAME
        spec["source_family"] = DEFAULT_APPWORLD_AGENT_NAME
        if "name" not in spec:
            spec["name"] = candidate.scaffold_name or DEFAULT_APPWORLD_AGENT_NAME
        if "source_project_path" not in spec and extra.get("source_project_path"):
            spec["source_project_path"] = str(extra["source_project_path"])
        return spec

    # ---- source snapshot (editable AppWorld agent.py) --------------------

    def _normalize_candidate_source_project_path(self, candidate: dict[str, Any]) -> None:
        extra = candidate.get("extra") if isinstance(candidate.get("extra"), dict) else {}
        if candidate.get("source_project_path"):
            return
        for key in ("source_project_path", "upstream_source_path", "appworld_source_path"):
            if extra.get(key):
                candidate["source_project_path"] = str(extra[key])
                return

    def _copy_upstream_source_context(self, source_family: str, dest_dir: Path) -> None:
        super()._copy_upstream_source_context(source_family, dest_dir)
        if source_family != DEFAULT_APPWORLD_AGENT_NAME:
            return
        root = dest_dir / "upstream_source" / "appworld"
        root.mkdir(parents=True, exist_ok=True)
        seed_agent = package_file("worldcalib.benchmarks.appworld", "agent.py")
        if seed_agent.exists():
            shutil.copy2(seed_agent, root / "agent.py")
        (root / "EDITABLE.md").write_text(
            "\n".join(
                [
                    "# AppWorld editable agent source",
                    "",
                    "Edit `agent.py` (the minimal ReAct code agent), then point",
                    "`source_project_path` at this dir",
                    "(`source_snapshot/candidate/upstream_source/appworld`) in",
                    'pending_eval.json with kind="appworld_agent".',
                    "",
                    "- `agent.py` — the WHOLE editable surface: the ReAct loop, the",
                    "  system prompt, API-doc discovery strategy, error handling, step",
                    "  budget, the SUT chat call. Keep it worldcalib-free (stdlib +",
                    "  openai + appworld only) and keep `solve(world)` returning a dict",
                    "  with steps/prompt_tokens/completion_tokens/error/transcript.",
                    "",
                    "Do NOT call world.evaluate() or read world.task.ground_truth (that",
                    "is grading). The SUT model is LOCKED — never change model/endpoint.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

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
        # Lineage: when building on a parent iter, replace the freshly seeded
        # upstream agent with the parent iteration's archived candidate source so
        # the proposer edits on top of it.
        if base_iter is not None:
            upstream = snapshot_root / "candidate" / "upstream_source" / "appworld"
            parent_upstream = (
                self._iteration_dir(base_iter)
                / "source_snapshot" / "candidate" / "upstream_source" / "appworld"
            )
            if parent_upstream.exists():
                if upstream.exists():
                    shutil.rmtree(upstream)
                shutil.copytree(
                    parent_upstream, upstream,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        return snapshot_root
