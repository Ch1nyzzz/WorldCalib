"""Terminal-Bench 2.0 optimization entry point for terminus-2 harness candidates.

Candidates are evaluated through the external ``harbor`` CLI. Terminal-Bench
tasks remain outside the editable snapshot, and candidate changes are limited to
the terminus-2 agent source.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.benchmark_workspaces import BenchmarkWorkspaceSpec, TB2_WORKSPACE_SPEC
from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.paths import resolve_external_path
from worldcalib.schemas import CandidateResult
from worldcalib.runners.harbor import (
    DEFAULT_HARBOR_BINARY,
    DEFAULT_REWARD_GATE,
    HarborTask,
)
from worldcalib.benchmarks.tb2.data import (
    DEFAULT_TB2_DATASET,
    PAPER_SANDBOX_STORAGE_CAP_MB,
    load_tb2_tasks,
)
from worldcalib.benchmarks.tb2.tb2 import (
    DEFAULT_TB2_AGENT,
    DEFAULT_TB2_API_BASE,
    DEFAULT_TB2_CONCURRENCY,
    DEFAULT_TB2_MODEL,
    DEFAULT_TB2_REPEATS,
    DEFAULT_TB2_SCAFFOLD_NAME,
    DEFAULT_TB2_TERMINUS2_SOURCE,
    TB2_API_BASE_KWARG,
    Tb2HarborRunner,
    run_tb2_frontier,
)

logger = logging.getLogger(__name__)

# Where, inside a candidate source snapshot, the editable terminus-2 package
# root lives (the parent dir of the importable ``terminus_2`` package). The
# runner puts this dir on PYTHONPATH and loads it via --agent-import-path.
_TERMINUS2_SNAPSHOT_RELROOT = Path("upstream_source") / "terminus2_agent_tb2"



@dataclass(frozen=True)
class Tb2OptimizerConfig(OptimizerConfig):
    """Configuration for terminus-2 harness optimization on Terminal-Bench 2.0."""

    tasks_path: Path | None = DEFAULT_TB2_DATASET
    terminus2_source_path: Path | None = DEFAULT_TB2_TERMINUS2_SOURCE
    harbor_binary: Path = DEFAULT_HARBOR_BINARY
    harbor_agent: str = DEFAULT_TB2_AGENT
    harbor_model: str = DEFAULT_TB2_MODEL
    # terminus-2 passes this endpoint to its model client.
    api_base: str = DEFAULT_TB2_API_BASE
    # Terminal-Bench's published methodology: pass@1 x 2 repeats.
    harbor_n_attempts: int = DEFAULT_TB2_REPEATS
    harbor_timeout_multiplier: float = 1.0
    harbor_concurrency: int = DEFAULT_TB2_CONCURRENCY
    # 0 = no cap; >0 caps the terminus-2 episode loop (--ak max_turns) so a
    # candidate's finalization gate cannot spin the agent forever.
    harbor_max_turns: int = 0
    # 0 = no cap; >0 = absolute per-task agent wall-clock ceiling in seconds
    # (graceful, via per-task --agent-timeout-multiplier).
    harbor_max_task_seconds: int = 0
    harbor_env_file: Path | None = None
    # harbor -e: trial sandbox backend. None = local docker; "daytona" = remote
    # Daytona sandboxes (prebuilt task images, no local docker networks).
    harbor_environment: str | None = None
    reward_gate: float = DEFAULT_REWARD_GATE
    # MEAN over the repeats, never max: "best" would take the luckiest of the k
    # trials, which is the aggregation Terminal-Bench's methodology explicitly
    # rules out and would spend the second repeat to *add* optimism instead of
    # removing noise.
    score_mode: str = "avg"
    task_ids: tuple[str, ...] = ()
    max_storage_mb: int = PAPER_SANDBOX_STORAGE_CAP_MB
    force: bool = False
    scaffolds: tuple[str, ...] = (DEFAULT_TB2_SCAFFOLD_NAME,)
    progressive_target_system: str = DEFAULT_TB2_SCAFFOLD_NAME


class Tb2Optimizer(LocomoOptimizer):
    """Proposer loop for Terminal-Bench 2.0 terminus-2 harness candidates."""

    workspace_spec: BenchmarkWorkspaceSpec = TB2_WORKSPACE_SPEC
    config: Tb2OptimizerConfig

    def __init__(self, config: Tb2OptimizerConfig) -> None:
        super().__init__(config)

    # -- example loading ----------------------------------------------------

    def _load_examples(self) -> list[HarborTask]:
        return load_tb2_tasks(
            self.config.tasks_path,
            split=self.config.split,
            limit=self.config.limit,
            task_ids=self.config.task_ids or (),
            max_storage_mb=self.config.max_storage_mb,
        )

    # -- seed frontier ------------------------------------------------------

    def _run_seed_frontier(self) -> dict[str, Any]:
        return run_tb2_frontier(
            out_dir=self.run_dir,
            tasks_path=self.config.tasks_path,
            split=self.config.split,
            limit=self.config.limit,
            task_ids=self.config.task_ids,
            max_storage_mb=self.config.max_storage_mb,
            harbor_binary=self.config.harbor_binary,
            harbor_agent=self.config.harbor_agent,
            harbor_model=self.config.harbor_model,
            api_base=self.config.api_base,
            n_attempts=self.config.harbor_n_attempts,
            timeout_multiplier=self.config.harbor_timeout_multiplier,
            concurrency=self.config.harbor_concurrency,
            max_turns=self.config.harbor_max_turns,
            max_task_seconds=self.config.harbor_max_task_seconds,
            env_file=self.config.harbor_env_file,
            harbor_environment=self.config.harbor_environment,
            reward_gate=self.config.reward_gate,
            score_mode=self.config.score_mode,
            eval_timeout_s=self.config.eval_timeout_s,
            max_eval_workers=self.config.max_eval_workers,
            dry_run=self.config.dry_run,
            force=self.config.force,
            pareto_quality_threshold=self.config.pareto_quality_threshold,
        )

    # -- prompt / policy naming --------------------------------------------

    def _benchmark_prompt_name(self) -> str:
        return "Terminal-Bench 2.0 terminus-2 optimization"

    def _raw_data_policy_name(self) -> str:
        return (
            "the Terminal-Bench verifier internals and the raw task tree "
            "(each record already carries its own task's solution as gold)"
        )

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {
            "benchmark": "tb2",
            "kind": "tb2",
            "scoring_method": "harbor_reward",
        }

    # -- runner construction ------------------------------------------------

    def _make_harbor_runner(
        self, tasks: list[HarborTask], *, out_dir: Path, n_attempts: int | None = None
    ) -> Tb2HarborRunner:
        return Tb2HarborRunner(
            tasks=tasks,
            out_dir=out_dir,
            harbor_binary=self.config.harbor_binary,
            harbor_agent=self.config.harbor_agent,
            harbor_model=self.config.harbor_model,
            n_attempts=(n_attempts if n_attempts is not None else self.config.harbor_n_attempts),
            timeout_multiplier=self.config.harbor_timeout_multiplier,
            concurrency=self.config.harbor_concurrency,
            max_turns=self.config.harbor_max_turns,
            max_task_seconds=self.config.harbor_max_task_seconds,
            env_file=self.config.harbor_env_file,
            harbor_environment=self.config.harbor_environment,
            reward_gate=self.config.reward_gate,
            score_mode=self.config.score_mode,
            eval_timeout_s=self.config.eval_timeout_s,
            max_eval_workers=self.config.max_eval_workers,
            dry_run=self.config.dry_run,
            force=self.config.force,
        )

    # -- editable terminus-2 source snapshot (Option B) ---------------------

    def _terminus2_source_root(self) -> Path:
        """Absolute path to the pristine terminus-2 source root (parent of the
        importable ``terminus_2`` package)."""
        return resolve_external_path(
            self.config.terminus2_source_path,
            env_var="TB2_TERMINUS2_SOURCE",
            label="terminus-2 source checkout",
        )

    def _copy_upstream_source_context(self, source_family: str, dest_dir: Path) -> None:
        """Seed an EDITABLE copy of the terminus-2 agent package into the
        candidate snapshot so the proposer can reshape its prompt templates and
        control flow. The runner loads the edited copy via --agent-import-path."""
        super()._copy_upstream_source_context(source_family, dest_dir)
        if source_family != self.config.progressive_target_system:
            return
        src_pkg = self._terminus2_source_root() / "terminus_2"
        if not src_pkg.is_dir():
            logger.warning(
                "terminus-2 source package not found at %s; candidate snapshot "
                "will have no editable agent (falls back to installed terminus-2).",
                src_pkg,
            )
            return
        dest_root = dest_dir / _TERMINUS2_SNAPSHOT_RELROOT
        dest_root.mkdir(parents=True, exist_ok=True)
        self._copy_tree_if_exists(src_pkg, dest_root / "terminus_2")
        # Read-only harbor interface contract (BaseAgent / BaseEnvironment /
        # AgentContext / LiteLLM …). The proposer's sandbox has no harbor install,
        # so without these it cannot design a from-scratch agent against the real
        # interface. Placed OUTSIDE the importable terminus_2 package (reference
        # only, never on PYTHONPATH).
        contract_src = self._terminus2_source_root() / "harbor_contract"
        if contract_src.is_dir():
            self._copy_tree_if_exists(
                contract_src, dest_dir / "upstream_source" / "harbor_contract"
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
        candidate_dir = snapshot_root / "candidate"
        agent_root = candidate_dir / _TERMINUS2_SNAPSHOT_RELROOT
        # CuraII lineage: when a parent base is supplied, replace the freshly
        # baseline-seeded terminus-2 copy with the parent iteration's edited
        # agent so the proposer edits on top of a previously evaluated candidate.
        if base_iter is not None:
            parent_agent = (
                self._iteration_dir(base_iter)
                / "source_snapshot"
                / "candidate"
                / _TERMINUS2_SNAPSHOT_RELROOT
                / "terminus_2"
            )
            if parent_agent.is_dir():
                if agent_root.exists():
                    shutil.rmtree(agent_root)
                agent_root.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    parent_agent,
                    agent_root / "terminus_2",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        (candidate_dir / "SNAPSHOT_TB2.md").write_text(
            "\n".join(
                [
                    "# Terminal-Bench 2.0 agent harness snapshot",
                    "",
                    f"Iteration: {iteration}",
                    "",
                    "You are designing the AGENT HARNESS that Terminal-Bench runs against",
                    "each task. The EDITABLE agent package is at:",
                    f"  {_TERMINUS2_SNAPSHOT_RELROOT}/terminus_2/",
                    "",
                    "`terminus_2/terminus_2.py` is the CURRENT implementation — a",
                    "REFERENCE you may keep, modify, or REPLACE WHOLESALE. Its whole",
                    "agent loop (how the model is called, how commands run, how output",
                    "is fed back, how/when it retries, what state persists across",
                    "attempts, when it finalizes) is yours to redesign. The only fixed",
                    "contract is the harbor `BaseAgent` interface: keep the entry class",
                    "`class Terminus2(BaseAgent)` in `terminus_2/terminus_2.py` and",
                    "implement `name()`, `version()`, `async setup(environment)`, and",
                    "`async run(instruction, environment, context)`. Everything inside",
                    "`run()` is free.",
                    "",
                    "The harbor interface you design against (READ-ONLY reference,",
                    "your sandbox has no harbor install) is mirrored at:",
                    "  upstream_source/harbor_contract/   (BaseAgent, BaseEnvironment +",
                    "  ExecResult, AgentContext, LiteLLM/Chat, TmuxSession)",
                    "Use `environment.exec(...)` to run commands in the task container",
                    "and a harbor LLM client to call the (fixed) solver model; see the",
                    "reference `terminus_2.py` for concrete usage of both.",
                    "",
                    "We do NOT prescribe a design — no required loop shape, memory,",
                    "retry, or multi-attempt scheme. Choose whatever mechanism the",
                    "traces justify; a from-scratch redesign and a small edit are both",
                    "valid candidates.",
                    "",
                    "Then in pending_eval.json set `extra.source_project_path` to the",
                    "ABSOLUTE path of the package ROOT (the parent of `terminus_2/`):",
                    f"  {agent_root}",
                    "",
                    "Do NOT touch any task's solution/ or tests/ or task.toml, and",
                    "never read solution/ or the verifier's reward files at task time.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        manifest_path = snapshot_root / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        manifest["terminus2_source"] = str(agent_root)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        call_manifest = call_dir / "source_snapshot_manifest.json"
        if call_manifest.exists():
            call_manifest.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return snapshot_root

    def _normalize_candidate_agent_source_path(
        self, candidate: dict[str, Any], iteration: int
    ) -> None:
        """Resolve the proposer's edited terminus-2 source root onto the candidate
        as an absolute ``agent_source_path`` the runner consumes.

        Invalid emitted paths are recovered from the canonical per-iteration
        snapshot before falling back to the configured pristine source."""

        def _valid(p: Path) -> bool:
            return (p / "terminus_2" / "terminus_2.py").is_file()

        def _abs(value: object) -> Path:
            p = Path(str(value)).expanduser()
            return p if p.is_absolute() else (self.project_root / p)

        # An already-set agent_source_path is authoritative only if it resolves.
        if candidate.get("agent_source_path"):
            p = _abs(candidate["agent_source_path"])
            if _valid(p):
                candidate["agent_source_path"] = str(p)
                return

        extra = candidate.get("extra") if isinstance(candidate.get("extra"), dict) else {}
        emitted: object | None = None
        for key in ("agent_source_path", "source_project_path", "terminus2_source_path"):
            value = candidate.get(key) or extra.get(key)
            if value:
                emitted = value
                path = _abs(value)
                if _valid(path):
                    candidate["agent_source_path"] = str(path)
                    return
                break

        # Emitted path missing/invalid → recover from the canonical snapshot root
        # the optimizer built for this iteration (the proposer's edits live there
        # regardless of the path string it reported), so a malformed path never
        # silently discards a real edited candidate.
        canonical = (
            self._iteration_dir(iteration)
            / "source_snapshot"
            / "candidate"
            / _TERMINUS2_SNAPSHOT_RELROOT
        )
        if _valid(canonical):
            if emitted is not None:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "agent_source_path_recovered",
                        "emitted": str(emitted),
                        "resolved": str(canonical),
                    }
                )
            candidate["agent_source_path"] = str(canonical)
            return

        candidate["agent_source_path"] = str(self._terminus2_source_root())

    def _apply_solver_endpoint(self, candidate: dict[str, Any]) -> None:
        """Pin every candidate to the frozen solver's endpoint.

        The model is fixed by the experiment configuration. An optional API
        endpoint is injected only when explicitly configured by the operator.
        """

        kwargs = candidate.get("agent_kwargs")
        kwargs = dict(kwargs) if isinstance(kwargs, dict) else {}
        if self.config.api_base:
            kwargs[TB2_API_BASE_KWARG] = self.config.api_base
        else:
            kwargs.pop(TB2_API_BASE_KWARG, None)
        candidate["agent_kwargs"] = kwargs
        candidate["model"] = self.config.harbor_model

    # -- proposed-candidate evaluation -------------------------------------

    def _evaluate_proposed(
        self,
        iteration: int,
        proposed: list[dict[str, Any]],
        examples: list[HarborTask],
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
                or DEFAULT_TB2_SCAFFOLD_NAME
            )
            candidate.setdefault("agent_name", agent_name)
            candidate.setdefault("scaffold_name", DEFAULT_TB2_SCAFFOLD_NAME)
            self._apply_solver_endpoint(candidate)
            self._normalize_candidate_agent_source_path(candidate, iteration)

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

    def _tb2_test_spec(self, candidate: CandidateResult) -> dict[str, Any]:
        config = dict(candidate.config) if isinstance(candidate.config, dict) else {}
        spec = dict(config)
        spec["candidate_id"] = self._test_candidate_id(candidate.candidate_id)
        spec["original_candidate_id"] = candidate.candidate_id
        spec["agent_name"] = str(
            spec.get("agent_name")
            or spec.get("scaffold_name")
            or candidate.scaffold_name
            or DEFAULT_TB2_SCAFFOLD_NAME
        )
        spec["scaffold_name"] = DEFAULT_TB2_SCAFFOLD_NAME
        if "name" not in spec:
            spec["name"] = candidate.scaffold_name or DEFAULT_TB2_SCAFFOLD_NAME
        return spec

    def _run_test_frontier(self, candidates: list[CandidateResult]) -> dict[str, Any]:
        full_frontier = self._quality_frontier(candidates)
        candidate_limit = max(0, int(self.config.test_frontier_candidate_limit or 0))
        frontier = full_frontier[:candidate_limit] if candidate_limit else full_frontier
        test_dir = self.run_dir / "test_frontier"
        specs_dir = test_dir / "candidate_specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        examples = load_tb2_tasks(
            self.config.tasks_path,
            split=self.config.test_split,
            limit=self.config.test_limit,
            max_storage_mb=self.config.max_storage_mb,
            task_ids=self.config.task_ids or None,
        )
        runner = self._make_harbor_runner(examples, out_dir=test_dir)

        rows: list[dict[str, Any]] = []
        test_results: list[CandidateResult] = []
        failures: list[dict[str, Any]] = []
        for candidate in frontier:
            spec = self._tb2_test_spec(candidate)
            spec_path = specs_dir / f"{spec['candidate_id']}.json"
            spec_path.write_text(
                json.dumps(spec, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                result = runner.evaluate_candidate(
                    candidate=spec,
                    candidate_id=str(spec["candidate_id"]),
                    agent_name=str(spec.get("agent_name") or DEFAULT_TB2_SCAFFOLD_NAME),
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
            "benchmark": "tb2",
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
