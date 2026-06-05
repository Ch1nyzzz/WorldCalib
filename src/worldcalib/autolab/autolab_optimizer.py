"""AutoLab optimization entry point for terminus-2 harness-config candidates.

Mirrors :mod:`worldcalib.coding.swebench_optimizer`: the candidate is a *config
dict* graded by shelling out to an external evaluator (here, the cyh_dev
``harbor`` binary), so we subclass :class:`LocomoOptimizer` directly — NOT
``SelfDistillOptimizer`` — and never call ``load_candidate_scaffold`` (there is
no in-process scaffold to import). The source-snapshot lockdown machinery
swebench needs (eval-gate mirroring, tamper detection) is unnecessary: AutoLab
tasks live in a canonical read-only dir, the verifier runs inside the harbor
docker container, and the candidate carries only config kwargs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.benchmark_workspaces import BenchmarkWorkspaceSpec
from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.schemas import CandidateResult
from worldcalib.autolab.autolab import (
    DEFAULT_AUTOLAB_AGENT,
    DEFAULT_AUTOLAB_MODEL,
    DEFAULT_AUTOLAB_SCAFFOLD_NAME,
    DEFAULT_AUTOLAB_TASKS_PATH,
    DEFAULT_HARBOR_BINARY,
    DEFAULT_HARBOR_PYTHON,
    DEFAULT_REWARD_GATE,
    AutolabHarborRunner,
    AutolabTask,
    load_autolab_tasks,
    run_autolab_frontier,
)


# AutoLab proposer workspace: a minimal importable source set (mirrors
# SWEBENCH_WORKSPACE_SPEC). The proposer optimizes config kwargs expressed in
# pending_eval.json, not this source tree, so an essentially-empty snapshot is
# fine. ``benchmark`` MUST equal "autolab" to match the trace adapter name and
# RunStore(benchmark=...).
AUTOLAB_WORKSPACE_SPEC = BenchmarkWorkspaceSpec(
    benchmark="autolab",
    primary_source_file="autolab/autolab.py",
    source_files=(
        "__init__.py",
        "benchmark_workspaces.py",
        "claude_runner.py",
        "autolab/__init__.py",
        "autolab/autolab.py",
        "autolab/autolab_optimizer.py",
        "model.py",
        "optimizer.py",
        "pareto.py",
        "post_eval.py",
        "proposer_prompt.py",
        "schemas.py",
    ),
)


@dataclass(frozen=True)
class AutolabOptimizerConfig(OptimizerConfig):
    """Configuration for terminus-2 harness-config optimization on AutoLab."""

    tasks_path: Path = DEFAULT_AUTOLAB_TASKS_PATH
    harbor_python: Path = DEFAULT_HARBOR_PYTHON
    harbor_binary: Path = DEFAULT_HARBOR_BINARY
    harbor_agent: str = DEFAULT_AUTOLAB_AGENT
    harbor_model: str = DEFAULT_AUTOLAB_MODEL
    harbor_n_attempts: int = 1
    harbor_timeout_multiplier: float = 1.0
    harbor_concurrency: int = 4
    harbor_env_file: Path | None = None
    reward_gate: float = DEFAULT_REWARD_GATE
    score_mode: str = "best"
    task_ids: tuple[str, ...] = ()
    force: bool = False
    verify_patches: bool = True
    scaffolds: tuple[str, ...] = (DEFAULT_AUTOLAB_SCAFFOLD_NAME,)
    progressive_target_system: str = DEFAULT_AUTOLAB_SCAFFOLD_NAME


class AutolabOptimizer(LocomoOptimizer):
    """Proposer loop for AutoLab terminus-2 harness-config candidates."""

    workspace_spec: BenchmarkWorkspaceSpec = AUTOLAB_WORKSPACE_SPEC
    config: AutolabOptimizerConfig

    def __init__(self, config: AutolabOptimizerConfig) -> None:
        super().__init__(config)

    # -- example loading ----------------------------------------------------

    def _load_examples(self) -> list[AutolabTask]:
        return load_autolab_tasks(
            self.config.tasks_path,
            split=self.config.split,
            limit=self.config.limit,
            task_ids=self.config.task_ids or None,
        )

    # -- seed frontier ------------------------------------------------------

    def _run_seed_frontier(self) -> dict[str, Any]:
        return run_autolab_frontier(
            out_dir=self.run_dir,
            tasks_path=self.config.tasks_path,
            split=self.config.split,
            limit=self.config.limit,
            task_ids=self.config.task_ids,
            harbor_binary=self.config.harbor_binary,
            harbor_python=self.config.harbor_python,
            harbor_agent=self.config.harbor_agent,
            harbor_model=self.config.harbor_model,
            n_attempts=self.config.harbor_n_attempts,
            timeout_multiplier=self.config.harbor_timeout_multiplier,
            concurrency=self.config.harbor_concurrency,
            env_file=self.config.harbor_env_file,
            reward_gate=self.config.reward_gate,
            eval_timeout_s=self.config.eval_timeout_s,
            max_eval_workers=self.config.max_eval_workers,
            dry_run=self.config.dry_run,
            force=self.config.force,
            verify_patches=self.config.verify_patches,
            pareto_quality_threshold=self.config.pareto_quality_threshold,
        )

    # -- prompt / policy naming --------------------------------------------

    def _benchmark_prompt_name(self) -> str:
        return "AutoLab terminus-2 optimization"

    def _raw_data_policy_name(self) -> str:
        return "AutoLab reference solutions and verifier internals"

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "autolab",
            "kind": "autolab",
            "scoring_method": "harbor_reward",
        }

    # -- runner construction ------------------------------------------------

    def _make_harbor_runner(
        self, tasks: list[AutolabTask], *, out_dir: Path
    ) -> AutolabHarborRunner:
        return AutolabHarborRunner(
            tasks=tasks,
            out_dir=out_dir,
            harbor_binary=self.config.harbor_binary,
            harbor_python=self.config.harbor_python,
            harbor_agent=self.config.harbor_agent,
            harbor_model=self.config.harbor_model,
            n_attempts=self.config.harbor_n_attempts,
            timeout_multiplier=self.config.harbor_timeout_multiplier,
            concurrency=self.config.harbor_concurrency,
            env_file=self.config.harbor_env_file,
            reward_gate=self.config.reward_gate,
            score_mode=self.config.score_mode,
            eval_timeout_s=self.config.eval_timeout_s,
            max_eval_workers=self.config.max_eval_workers,
            dry_run=self.config.dry_run,
            force=self.config.force,
            verify_patches=self.config.verify_patches,
        )

    # -- proposed-candidate evaluation -------------------------------------

    def _evaluate_proposed(
        self,
        iteration: int,
        proposed: list[dict[str, Any]],
        examples: list[AutolabTask],
    ) -> list[CandidateResult]:
        runner = self._make_harbor_runner(examples, out_dir=self.run_dir)
        results: list[CandidateResult] = []
        for raw in proposed:
            if not isinstance(raw, dict):
                continue
            candidate = dict(raw)
            agent_name = str(
                candidate.get("agent_name")
                or candidate.get("scaffold_name")
                or DEFAULT_AUTOLAB_SCAFFOLD_NAME
            )
            candidate.setdefault("agent_name", agent_name)
            candidate.setdefault("scaffold_name", DEFAULT_AUTOLAB_SCAFFOLD_NAME)

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

    # -- test frontier ------------------------------------------------------

    def _autolab_test_spec(self, candidate: CandidateResult) -> dict[str, Any]:
        config = dict(candidate.config) if isinstance(candidate.config, dict) else {}
        spec = dict(config)
        spec["candidate_id"] = self._test_candidate_id(candidate.candidate_id)
        spec["original_candidate_id"] = candidate.candidate_id
        spec["agent_name"] = str(
            spec.get("agent_name")
            or spec.get("scaffold_name")
            or candidate.scaffold_name
            or DEFAULT_AUTOLAB_SCAFFOLD_NAME
        )
        spec["scaffold_name"] = DEFAULT_AUTOLAB_SCAFFOLD_NAME
        if "name" not in spec:
            spec["name"] = candidate.scaffold_name or DEFAULT_AUTOLAB_SCAFFOLD_NAME
        return spec

    def _run_test_frontier(self, candidates: list[CandidateResult]) -> dict[str, Any]:
        full_frontier = self._quality_frontier(candidates)
        candidate_limit = max(0, int(self.config.test_frontier_candidate_limit or 0))
        frontier = full_frontier[:candidate_limit] if candidate_limit else full_frontier
        test_dir = self.run_dir / "test_frontier"
        specs_dir = test_dir / "candidate_specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        examples = load_autolab_tasks(
            self.config.tasks_path,
            split=self.config.test_split,
            limit=self.config.test_limit,
            task_ids=self.config.task_ids or None,
        )
        runner = self._make_harbor_runner(examples, out_dir=test_dir)

        rows: list[dict[str, Any]] = []
        test_results: list[CandidateResult] = []
        failures: list[dict[str, Any]] = []
        for candidate in frontier:
            spec = self._autolab_test_spec(candidate)
            spec_path = specs_dir / f"{spec['candidate_id']}.json"
            spec_path.write_text(
                json.dumps(spec, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                result = runner.evaluate_candidate(
                    candidate=spec,
                    candidate_id=str(spec["candidate_id"]),
                    agent_name=str(spec.get("agent_name") or DEFAULT_AUTOLAB_SCAFFOLD_NAME),
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

        results_path = test_dir / "test_results.json"
        results_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
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
            "benchmark": "autolab",
            "split": self.config.test_split,
            "limit": self.config.test_limit,
            "count": len(examples),
            "train_frontier_total_count": len(full_frontier),
            "candidate_limit": candidate_limit,
            "train_frontier_count": len(frontier),
            "evaluated_count": len(test_results),
            "failed_count": len(failures),
            "test_dir": str(test_dir),
            "test_results_path": str(results_path),
            "test_pareto_frontier_path": str(test_frontier_path),
            "candidate_spec_dir": str(specs_dir),
            "failures": failures,
        }
        summary_path = self.run_dir / "test_frontier_summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        summary["summary_path"] = str(summary_path)
        return summary
