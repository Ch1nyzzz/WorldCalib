"""Claude Code proposer optimization loop for OptiHarness."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.baseline import load_baseline_candidates
from worldcalib.benchmark_workspaces import (
    LOCOMO_WORKSPACE_SPEC,
    BenchmarkWorkspaceSpec,
    copy_benchmark_project_source,
)
from worldcalib.claude_runner import (
    DEFAULT_DOCKER_ENV_VARS,
    ProposerSandboxConfig,
    _float_metric,
    _int_metric,
    run_code_agent_prompt,
)
from worldcalib.dynamic import load_candidate_scaffold
from worldcalib.evaluation import EvaluationRunner, run_initial_frontier
from worldcalib.memory.locomo import (
    default_data_path,
    load_locomo_examples,
    prepare_locomo,
    select_split,
)
from worldcalib.model import DEFAULT_BASE_URL, DEFAULT_MODEL
from worldcalib.optimization_cells import get_target_cells
from worldcalib.pareto import ParetoPoint, pareto_frontier, save_frontier
from worldcalib.post_eval import write_diff_digest, write_post_eval_artifacts
from worldcalib.run_store import RunStore, diff_stats
from worldcalib.traces import TraceHarness, has_adapter
from worldcalib.proposer_prompt import build_progressive_proposer_prompt
from worldcalib.memory.scaffolds import (
    DEFAULT_MEMORY_EVOLUTION_SEED_SCAFFOLDS as DEFAULT_EVOLUTION_SEED_SCAFFOLDS,
    DEFAULT_MEMORY_SCAFFOLD_TOP_KS as DEFAULT_SCAFFOLD_TOP_KS,
)
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.schemas import CandidateResult, LocomoExample


DEFAULT_PROPOSER_DOCKER_IMAGE = "docker-claude:latest"


def _pending_candidates(payload: Any) -> list[Any]:
    """Accept either {"candidates": [...]} or a top-level candidate list."""

    if isinstance(payload, dict):
        candidates = payload.get("candidates") or []
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    return candidates if isinstance(candidates, list) else []


@dataclass(frozen=True)
class OptimizerConfig:
    """Configuration for the Claude Code proposer loop."""

    run_id: str
    out_dir: Path
    iterations: int = 20
    split: str = "train"
    limit: int = 0
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key: str = "EMPTY"
    eval_timeout_s: int = 300
    proposer_agent: str = "claude"
    claude_model: str = "deepseek-v4-pro[1m]"
    claude_effort: str = ""
    claude_base_url: str = "https://api.deepseek.com/anthropic"
    claude_auth_token: str | None = None
    claude_native_auth: bool = False
    # Codex proposer settings (used only when proposer_agent == "codex").
    # Codex authenticates from $CODEX_HOME/auth.json (default ~/.codex),
    # not via env tokens, so there is no codex_auth_token field.
    codex_model: str = "gpt-5.5"
    codex_reasoning_effort: str = "high"
    codex_home: str = ""
    propose_timeout_s: int = 2400
    # Grace window (seconds) after a docker proposer overruns
    # ``propose_timeout_s``: we poll for the workspace ``pending_eval.json`` to
    # finish flushing before ``docker kill``-ing the orphaned container. Short
    # by design — it only wins the boundary race where a candidate lands at the
    # wire; overrun candidates that land many minutes late are unsalvageable
    # without defeating the timeout.
    propose_salvage_grace_s: int = 60
    dry_run: bool = False
    max_context_chars: int = 6000
    max_eval_workers: int = 1
    skip_scaffold_eval: bool = False
    resume: bool = False
    # When a proposer invocation reports an Anthropic usage-limit rejection
    # (HTTP 429 / rejected rate_limit_event), sleep until the limit window
    # resets and retry the same invocation instead of burning the iteration.
    wait_on_rate_limit: bool = True
    rate_limit_buffer_s: int = 120
    rate_limit_default_wait_s: int = 1800
    rate_limit_max_wait_s: int = 6 * 3600
    rate_limit_max_retries: int = 8
    rate_limit_poll_log_s: int = 300
    baseline_dir: Path | None = None
    scaffolds: tuple[str, ...] = DEFAULT_EVOLUTION_SEED_SCAFFOLDS
    scaffold_extra: dict[str, dict[str, object]] | None = None
    # "self" (default): the harness materialises the lex-best candidate
    # (passrate desc, average_score desc, later iter wins ties) as the patch
    # base, writes frontier_manifest.json + task_score_matrix.json into the
    # workspace, and the PROPOSER decides what to actually build on — it may
    # keep the default base, wholesale-copy any prior iter's source from
    # reference_iterations/iter_NNN/source_snapshot/, or graft files across
    # iters, declaring its chosen base in the candidate config. "default":
    # always re-baseline from the clean seed snapshot (no resampling).
    selection_policy: str = "self"
    include_optimization_direction: bool = False
    force_budget: str = ""
    progressive_target_system: str = "memgpt"
    progressive_initial_low_iterations: int = 5
    progressive_low_best_count: int = 1
    progressive_medium_best_count: int = 3
    pareto_quality_threshold: float = 0.125
    proposer_sandbox: str = "none"
    proposer_docker_image: str = ""
    proposer_docker_workspace: str = "/workspace"
    proposer_docker_env: tuple[str, ...] = ()
    proposer_docker_mount: tuple[str, ...] = ()
    proposer_docker_user: str = ""
    proposer_docker_home: str = ""
    test_frontier: bool = False
    test_split: str = "test"
    test_limit: int = 0
    test_frontier_candidate_limit: int = 0
    trace_baseline_path: Path | None = None
    proposer_show_trace_harness_section: bool = True
    # When False, the cumulative cross-session summary (the workspace
    # ``summaries/`` directory of structured logs, and the corresponding
    # prompt section) is withheld from the proposer -- the no-summary probe.
    summaries_in_workspace: bool = True
    # Organized mode uses generated state.md + RunStore tools as the
    # proposer's historical interface. Summaries remain generated on the
    # run side for compatibility, but are not copied into the workspace.
    organized: bool = False
    organized_state_md: bool = True
    organized_include_summaries: bool = False
    # Proposer world-model variant. "calib" (default) = self-distill WMC: the
    # append-only world_model_calibration.md protocol + a per-iter
    # prediction.md the proposer self-grades next iter (no external critic).
    # "nowmc" = pure-default ablation with no calibration protocol at all.
    proposer_variant: str = "calib"
    # Before the full eval, run the candidate on this many probe tasks; if it
    # produces zero model output on all of them (a runtime crash like the
    # KeyError that wiped iter_29), skip it instead of burning a full eval.
    # 0 disables the probe (default).
    dry_run_probe_k: int = 0
    # --- Designer mode (long autonomous session; AutoLab only) ---
    # When True, run() skips the per-iteration loop and launches ONE long
    # proposer session that owns the design rhythm: it edits the editable agent
    # source freely, calls an eval tool (worldcalib-eval) on a train subset
    # whenever it wants to verify, keeps a design log, and checkpoints converged
    # designs (worldcalib-checkpoint). The harness scores every checkpoint on
    # the held-out test split after the session and picks a winner. Eval runs
    # host-side via a file bridge (the sandbox has no harbor). Only the AutoLab
    # optimizer implements this; the base class raises NotImplementedError.
    designer: bool = False
    # Goal-loop: the model judges convergence (via done.py), but may not stop
    # until it has implemented+evaluated+checkpointed >= designer_min_directions
    # genuinely-different CODE-LEVEL directions. The loop re-invokes the designer
    # (continuation) up to designer_max_rounds times until that floor is met and
    # convergence is declared (or a safety ceiling trips). designer_session_
    # timeout_s is the PER-ROUND inner-agent timeout.
    designer_min_directions: int = 3
    designer_max_rounds: int = 6
    designer_session_timeout_s: int = 4 * 3600
    designer_confirm_attempts: int = 2  # harbor -k for held-out selection (noise reduction)
    # The agent freely chooses which tasks to eval; cost is capped (safety net)
    # by the cumulative number of harbor task-runs and eval submissions, plus
    # wall-clock — generous, so the loop stops on the goal, not the quota.
    designer_max_eval_calls: int = 200
    designer_max_task_runs: int = 600
    designer_max_wall_clock_s: int = 11 * 3600
    # The `--subset smoke` shortcut subset (a cheap default when the agent does
    # not name tasks). Empty → a few CPU-only train tasks, smallest first.
    designer_smoke_task_ids: tuple[str, ...] = ()
    designer_smoke_size: int = 3


class LocomoOptimizer:
    """Meta-harness-style proposer loop for LOCOMO memory scaffolds."""

    workspace_spec: BenchmarkWorkspaceSpec = LOCOMO_WORKSPACE_SPEC

    def __init__(self, config: OptimizerConfig) -> None:
        self.config = config
        self.project_root = Path(__file__).resolve().parents[2]
        self.run_dir = config.out_dir
        self.pending_eval_path = self.run_dir / "pending_eval.json"
        self.frontier_path = self.run_dir / "best_candidates.json"
        self.summary_path = self.run_dir / "evolution_summary.jsonl"
        self.generated_dir = self.run_dir / "generated"
        self.candidate_score_table_path = self.run_dir / "candidate_score_table.json"
        self.retrieval_diagnostics_summary_path = (
            self.run_dir / "retrieval_diagnostics_summary.json"
        )
        self.iteration_index_path = self.run_dir / "iteration_index.json"
        self.diff_summary_path = self.run_dir / "diff_summary.jsonl"
        self._validate_proposer_sandbox_policy()
        self._validate_proposer_agent()
        self.run_store = RunStore(
            self.run_dir,
            benchmark=self.workspace_spec.benchmark,
        )
        self.trace_harness: TraceHarness = self._build_trace_harness()

    def _build_trace_harness(self) -> TraceHarness:
        benchmark = self.workspace_spec.benchmark
        if not has_adapter(benchmark):
            raise ValueError(
                f"No trace adapter is registered for benchmark "
                f"{benchmark!r}. Register one in worldcalib.traces.adapters."
            )
        return TraceHarness(
            run_dir=self.run_dir,
            benchmark=benchmark,
            baseline_path=self.config.trace_baseline_path,
        )

    def _validate_proposer_agent(self) -> None:
        agent = self.config.proposer_agent.strip().lower()
        if agent not in {"claude", "codex"}:
            raise ValueError(
                "proposer_agent must be 'claude' or 'codex'; got "
                f"proposer_agent={self.config.proposer_agent!r}"
            )

    def _validate_proposer_sandbox_policy(self) -> None:
        policy = self.config.selection_policy.strip().lower()
        if policy not in {"self", "default"}:
            raise ValueError(
                f"unknown selection_policy={policy!r} (expected 'self' or 'default')"
            )

    def run(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_package_dirs(self.generated_dir)
        examples = self._load_examples()

        candidates: list[CandidateResult] = []
        if self.config.baseline_dir is not None:
            # Only filter on top_k for scaffolds that define one in
            # DEFAULT_SCAFFOLD_TOP_KS (memgpt_source, bm25, ...). Source-only
            # scaffolds like mini_swe_agent_source carry no top_k in their
            # candidate config, so applying the filter would reject every
            # candidate and break --baseline-dir on the SWE-bench / Terminus
            # tasks. Passing None when the dict is empty also lets a user
            # reuse an arbitrary baseline that was built without top_k
            # variants.
            top_k_filter = {
                scaffold: DEFAULT_SCAFFOLD_TOP_KS[scaffold]
                for scaffold in self.config.scaffolds
                if scaffold in DEFAULT_SCAFFOLD_TOP_KS
            }
            baseline_candidates = load_baseline_candidates(
                self.config.baseline_dir,
                split=self.config.split,
                scaffolds=self.config.scaffolds,
                top_k_by_scaffold=top_k_filter or None,
            )
            if not baseline_candidates:
                raise ValueError(
                    f"No baseline candidates found for split '{self.config.split}' "
                    f"under {self.config.baseline_dir}"
                )
            for item in baseline_candidates:
                candidate = CandidateResult.from_dict(item)
                if int(candidate.count) != len(examples):
                    raise ValueError(
                        "Baseline candidate count does not match current evaluation set: "
                        f"{candidate.candidate_id} has count={candidate.count}, "
                        f"but split={self.config.split!r} limit={self.config.limit} "
                        f"selects {len(examples)} examples. Recompute the baseline with "
                        "the same split/limit before using it as --baseline-dir."
                    )
                candidates.append(candidate)
                self._append_summary(iteration=0, candidate=candidate)
        elif not (self.config.skip_scaffold_eval or self.config.resume):
            scaffold_summary = self._run_seed_frontier()
            for item in scaffold_summary.get("candidates", []):
                candidate = CandidateResult.from_dict(item)
                candidates.append(candidate)
                self._append_summary(iteration=0, candidate=candidate)
        else:
            if self.config.resume and not (self.run_dir / "candidate_results").exists():
                raise ValueError(
                    f"--resume: no candidate_results/ under {self.run_dir}; "
                    "nothing to resume from."
                )
            candidates.extend(self._load_existing_candidates())
            if self.config.resume and not candidates:
                raise ValueError(
                    f"--resume: candidate_results/ under {self.run_dir} is empty "
                    "or unreadable; nothing to resume from."
                )

        # When resume is combined with --baseline-dir, branch A above only
        # loads iter-0 baseline candidates; we still need iter-1+ existing
        # candidates from this run's candidate_results so
        # _resume_start_iteration can pick up where the crashed run left off.
        # (Without this, max(completed) collapses to 0 and resume restarts
        # from iter 1, silently re-doing all completed iterations.)
        if self.config.resume and self.config.baseline_dir is not None:
            existing_ids = {c.candidate_id for c in candidates}
            for candidate in self._load_existing_candidates():
                if candidate.candidate_id not in existing_ids:
                    candidates.append(candidate)

        # Reusing scaffold/baseline rows is mutually exclusive with resume;
        # resume always reloads from candidate_results and never re-records
        # iteration 0, exactly like --skip-scaffold-eval.
        skip_iter0_recording = self.config.skip_scaffold_eval or self.config.resume

        start_iteration = 1
        if self.config.resume:
            start_iteration = self._resume_start_iteration(candidates)
            # Drop any stale per-iteration artifacts for the iterations we
            # are about to (re)run — these may exist as crashed/partial dirs
            # plus dangling evolution_summary / diff_summary rows.
            self._clean_stale_iteration_artifacts(start_iteration)

        if candidates and not skip_iter0_recording:
            best_ids = self._quality_frontier_ids(candidates)
            write_post_eval_artifacts(
                run_dir=self.run_dir,
                call_dir=None,
                iteration=0,
                candidates=candidates,
                frontier_ids=best_ids,
            )
            self.trace_harness.record_iteration(
                iteration=0,
                candidates=candidates,
                selection_policy=self.config.selection_policy,
            )
            self.run_store.record_eval(0, candidates)
            self.run_store.commit_iteration(0)
            self._refresh_run_store(0)

        self._save_best_candidates(candidates)
        self._refresh_run_indexes(candidates)

        # Designer mode replaces the per-iteration loop with one long
        # self-directed session (see OptimizerConfig.designer). The iter0 seed
        # frontier above gives it a baseline; everything after is owned by the
        # designer agent + the host eval bridge.
        if self.config.designer:
            return self._run_designer_session(examples, candidates)

        for iteration in range(start_iteration, self.config.iterations + 1):
            budget = self.config.force_budget or "high"
            evaluated = self._run_progressive_proposer_iteration(
                iteration,
                candidates,
                examples,
                budget=budget,
                adaptive=self.config.selection_policy == "self",
                selection_policy=self.config.selection_policy,
            )
            candidates.extend(evaluated)
            self._save_best_candidates(candidates)
            self._refresh_run_indexes(candidates)
            best_ids = self._quality_frontier_ids(candidates)
            write_post_eval_artifacts(
                run_dir=self.run_dir,
                call_dir=None,
                iteration=iteration,
                candidates=evaluated,
                frontier_ids=best_ids,
            )
            self.trace_harness.record_iteration(
                iteration=iteration,
                candidates=evaluated,
            )
            self.run_store.record_eval(iteration, evaluated)
            self._refresh_run_store(iteration)

        test_frontier_summary = (
            self._run_test_frontier(candidates)
            if self.config.test_frontier
            else None
        )

        final_summary = {
            "run_id": self.config.run_id,
            "out_dir": str(self.run_dir),
            "iterations": self.config.iterations,
            "candidate_count": len(candidates),
            "best_candidates_path": str(self.frontier_path),
            "selection_policy": self.config.selection_policy,
            "proposer_metrics": self._aggregate_proposer_metrics(),
        }
        if test_frontier_summary is not None:
            final_summary["test_frontier"] = test_frontier_summary
        (self.run_dir / "optimizer_summary.json").write_text(
            json.dumps(final_summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return final_summary

    def _run_designer_session(
        self,
        examples: list[Any],
        candidates: list[CandidateResult],
    ) -> dict[str, Any]:
        """Run one long autonomous designer session (see config.designer).

        Only benchmarks whose eval can be exposed as a host-side tool implement
        this; the base loop has no such bridge."""

        raise NotImplementedError(
            "designer mode is only implemented for the AutoLab optimizer "
            "(eval is served by a host-side bridge that runs harbor)."
        )

    def _run_default_proposer_iteration(
        self,
        iteration: int,
        examples: list[LocomoExample],
        existing_candidates: list[CandidateResult] | None = None,
    ) -> list[CandidateResult]:
        return self._run_progressive_proposer_iteration(
            iteration,
            existing_candidates or [],
            examples,
            budget="high",
            adaptive=False,
        )

    def _run_progressive_proposer_iteration(
        self,
        iteration: int,
        existing_candidates: list[CandidateResult],
        examples: list[LocomoExample],
        *,
        budget: str,
        adaptive: bool,
        selection_policy: str | None = None,
    ) -> list[CandidateResult]:
        if self.pending_eval_path.exists():
            self.pending_eval_path.unlink()
        call_dir = self.run_dir / "proposer_calls" / f"iter_{iteration:03d}"
        retry_note = ""
        max_attempts = 2
        result: Any | None = None
        workspace_dir = call_dir / "workspace"
        workspace_generated_dir = workspace_dir / "generated"
        reference_iterations: tuple[int, ...] = ()
        policy_name = selection_policy or ("self" if adaptive else "default")
        selected_base_iter: int | None = None
        selected_base_passrate: float | None = None
        selected_base_average_score: float | None = None
        selected_refs_override: tuple[int, ...] | None = None
        if policy_name == "self":
            selected_base_iter = self._self_select_default_base(
                existing_candidates,
                iteration=iteration,
            )
            selected_refs_override = None
        if selected_base_iter is not None:
            base_candidate = next(
                (
                    item
                    for item in existing_candidates
                    if _candidate_iteration(item.candidate_id)
                    == selected_base_iter
                ),
                None,
            )
            if base_candidate is not None:
                selected_base_passrate = base_candidate.passrate
                selected_base_average_score = base_candidate.average_score
        state_base_iter = selected_base_iter
        if self.config.organized and state_base_iter is None:
            state_base_iter = self._state_snapshot_base_iteration(
                existing_candidates,
                iteration=iteration,
            )
        self.run_store.begin_iteration(
            iteration,
            as_of_iteration=max(0, iteration - 1),
            base_iteration=state_base_iter if self.config.organized else selected_base_iter,
            status="running",
        )
        if self.config.organized and self.config.organized_state_md:
            self._write_state_md(
                iteration=iteration,
                as_of_iteration=max(0, iteration - 1),
                base_iteration=state_base_iter,
            )
        for attempt in range(1, max_attempts + 1):
            refs_override = selected_refs_override
            workspace_dir, reference_iterations = self._build_progressive_workspace(
                iteration=iteration,
                budget=budget,
                existing_candidates=existing_candidates,
                call_dir=call_dir,
                reference_iterations_override=refs_override,
                base_iter=selected_base_iter,
            )
            workspace_generated_dir = workspace_dir / "generated"
            workspace_source_snapshot_dir = workspace_dir / "source_snapshot"
            workspace_pending_eval_path = workspace_dir / "pending_eval.json"
            workspace_traces_dir = workspace_dir / "traces"
            # The proposer receives its self-contained benchmark skill via
            # the system-prompt channel (Claude --append-system-prompt /
            # Codex AGENTS.md); the user message carries only the
            # per-iteration assignment.
            prompt = build_progressive_proposer_prompt(
                run_id=self.config.run_id,
                iteration=iteration,
                run_dir=workspace_dir,
                pending_eval_path=workspace_pending_eval_path,
                summaries_dir=workspace_dir / "summaries",
                include_summaries=self._summaries_in_workspace_enabled(),
                reference_iterations_dir=workspace_dir / "reference_iterations",
                generated_dir=workspace_generated_dir,
                source_snapshot_dir=workspace_source_snapshot_dir,
                budget=budget,
                reference_iterations=reference_iterations,
                target_system=self.config.progressive_target_system,
                optimization_directions=(
                    self._optimization_direction_lines(self.config.progressive_target_system)
                    if self.config.include_optimization_direction
                    else ()
                ),
                split=self.config.split,
                limit=self.config.limit,
                selection_policy=policy_name,
                benchmark_name=self._benchmark_prompt_name(),
                current_base_iter=selected_base_iter,
                current_base_passrate=selected_base_passrate,
                current_base_average_score=selected_base_average_score,
                state_path=(
                    workspace_dir / "state.md"
                    if self.config.organized and self.config.organized_state_md
                    else None
                ),
                organized=self.config.organized,
                trace_harness_dir=(
                    workspace_traces_dir
                    if self.config.proposer_show_trace_harness_section
                    else None
                ),
            )
            if retry_note:
                prompt = f"{prompt}\n\n{retry_note}"
            result = self._run_proposer_agent(
                prompt,
                log_dir=call_dir / "agent" / f"attempt_{attempt:02d}",
                name="proposer",
                cwd=workspace_dir,
            )
            self._append_proposer_result_event(
                iteration=iteration,
                result=result,
                selection_policy=policy_name,
                extra={
                    "budget": budget,
                    "reference_iterations": list(reference_iterations),
                    "target_system": self.config.progressive_target_system,
                    "call_dir": str(call_dir),
                    "workspace_dir": str(workspace_dir),
                    "attempt": attempt,
                },
            )
            access_violations = self._proposer_access_violations(
                result,
                workspace_dir=workspace_dir,
            )
            if not access_violations:
                break
            if attempt < max_attempts:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "proposer_access_retry",
                        "selection_policy": policy_name,
                        "budget": budget,
                        "attempt": attempt,
                        "violations": access_violations,
                    }
                )
                retry_note = self._access_retry_note(
                    violations=access_violations,
                    workspace_dir=workspace_dir,
                )
                continue
            self._append_event(
                {
                    "iteration": iteration,
                    "event": "proposer_access_rejected",
                    "selection_policy": policy_name,
                    "budget": budget,
                    "attempt": attempt,
                    "violations": access_violations,
                }
            )
            return []

        assert result is not None
        self._archive_workspace_outputs(
            workspace_dir=workspace_dir,
            call_dir=call_dir,
            result=result,
        )
        if (
            result.returncode == 0
            and not result.timed_out
            and not self.pending_eval_path.exists()
        ):
            self._append_event(
                {
                    "iteration": iteration,
                    "event": "proposer_missing_pending_retry",
                    "selection_policy": policy_name,
                    "budget": budget,
                    "attempt": max_attempts,
                }
            )
            repair_prompt = (
                f"{prompt}\n\n"
                "## Required Repair\n\n"
                "The previous proposer attempt exited without writing "
                f"`{workspace_pending_eval_path}`. Continue in the same "
                "workspace, make a concrete candidate source change if needed, "
                "and write exactly one valid `pending_eval.json`. Do not run "
                "the full harness evaluation."
            )
            result = self._run_proposer_agent(
                repair_prompt,
                log_dir=call_dir / "agent" / "missing_pending_retry",
                name="proposer",
                cwd=workspace_dir,
            )
            self._append_proposer_result_event(
                iteration=iteration,
                result=result,
                selection_policy=policy_name,
                extra={
                    "budget": budget,
                    "reference_iterations": list(reference_iterations),
                    "target_system": self.config.progressive_target_system,
                    "call_dir": str(call_dir),
                    "workspace_dir": str(workspace_dir),
                    "attempt": "missing_pending_retry",
                },
            )
            access_violations = self._proposer_access_violations(
                result,
                workspace_dir=workspace_dir,
            )
            if access_violations:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "proposer_access_rejected",
                        "selection_policy": policy_name,
                        "budget": budget,
                        "attempt": "missing_pending_retry",
                        "violations": access_violations,
                    }
                )
                return []
            self._archive_workspace_outputs(
                workspace_dir=workspace_dir,
                call_dir=call_dir,
                result=result,
            )
        proposer_unclean = result.returncode != 0 or result.timed_out
        if not self.pending_eval_path.exists() or (
            proposer_unclean and not self._pending_eval_is_salvageable()
        ):
            self._append_event(
                {
                    "iteration": iteration,
                    "event": "proposer_failed",
                    "selection_policy": policy_name,
                    "budget": budget,
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "stderr": result.stderr[:1000],
                    "proposer_metrics": getattr(result, "metrics", {}),
                }
            )
            return []
        if proposer_unclean:
            # Salvage a candidate the proposer had already finished writing
            # before it was killed. max-effort sessions
            # routinely complete pending_eval.json but fail to exit within
            # propose_timeout_s; the kill (returncode=None) also drops the
            # final usage message, so metrics show 0 tokens even though a
            # full iteration's worth of work landed on disk. Discarding it
            # wastes the whole iteration — instead we keep the candidate and
            # let the normal parse / critic / access gates below validate it.
            self._append_event(
                {
                    "iteration": iteration,
                    "event": "proposer_candidate_recovered_after_failure",
                    "selection_policy": policy_name,
                    "budget": budget,
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                    "proposer_metrics": getattr(result, "metrics", {}),
                }
            )

        try:
            pending = json.loads(self.pending_eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self._append_event(
                {
                    "iteration": iteration,
                    "event": "proposer_invalid_pending_retry",
                    "selection_policy": policy_name,
                    "budget": budget,
                    "attempt": "json_parse_retry",
                    "error": str(exc),
                }
            )
            repair_prompt = (
                f"{prompt}\n\n"
                "## Required Repair\n\n"
                f"The previous proposer wrote invalid JSON to `{workspace_pending_eval_path}`: "
                f"{exc}. Rewrite that file as exactly one valid JSON object with a "
                "`candidates` array containing one candidate. Escape backslashes inside "
                "strings as `\\\\`, or remove them. Do not run the full harness evaluation."
            )
            result = self._run_proposer_agent(
                repair_prompt,
                log_dir=call_dir / "agent" / "invalid_pending_retry",
                name="proposer",
                cwd=workspace_dir,
            )
            self._append_proposer_result_event(
                iteration=iteration,
                result=result,
                selection_policy=policy_name,
                extra={
                    "budget": budget,
                    "reference_iterations": list(reference_iterations),
                    "target_system": self.config.progressive_target_system,
                    "call_dir": str(call_dir),
                    "workspace_dir": str(workspace_dir),
                    "attempt": "invalid_pending_retry",
                },
            )
            access_violations = self._proposer_access_violations(
                result,
                workspace_dir=workspace_dir,
            )
            if access_violations:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "proposer_access_rejected",
                        "selection_policy": policy_name,
                        "budget": budget,
                        "attempt": "invalid_pending_retry",
                        "violations": access_violations,
                    }
                )
                return []
            self._archive_workspace_outputs(
                workspace_dir=workspace_dir,
                call_dir=call_dir,
                result=result,
            )
            if result.returncode != 0 or result.timed_out or not self.pending_eval_path.exists():
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "proposer_failed",
                        "selection_policy": policy_name,
                        "budget": budget,
                        "returncode": result.returncode,
                        "timed_out": result.timed_out,
                        "stderr": result.stderr[:1000],
                        "proposer_metrics": getattr(result, "metrics", {}),
                    }
                )
                return []
            try:
                pending = json.loads(self.pending_eval_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as retry_exc:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "proposer_invalid_pending_rejected",
                        "selection_policy": policy_name,
                        "budget": budget,
                        "attempt": "invalid_pending_retry",
                        "error": str(retry_exc),
                    }
                )
                return []
        proposed = _pending_candidates(pending)
        if len(proposed) != 1:
            self._append_event(
                {
                    "iteration": iteration,
                    "event": "candidate_count_adjusted",
                    "selection_policy": policy_name,
                    "budget": budget,
                    "requested_count": len(proposed),
                    "evaluated_count": min(len(proposed), 1),
                }
            )
            proposed = proposed[:1]
        for raw in proposed:
            if isinstance(raw, dict):
                self._normalize_workspace_candidate_paths(
                    raw,
                    workspace_dir=workspace_dir,
                    workspace_generated_dir=workspace_generated_dir,
                )
                self._rewrite_workspace_source_paths_to_archive(
                    raw,
                    workspace_dir=workspace_dir,
                    archived_source_snapshot=call_dir / "source_snapshot",
                )
                raw.setdefault("source_family", self.config.progressive_target_system)
                raw.setdefault("budget", budget)
                raw.setdefault("reference_iterations", list(reference_iterations))
                raw.setdefault("source_snapshot_path", str(call_dir / "source_snapshot"))
                # The optimizer authoritatively owns the candidate ``kind`` (which
                # backend loader runs it). The proposer is told to set it but
                # occasionally omits it, and a missing kind silently routes an
                # agent / tau2 / arc candidate to the MEMORY loader, which rejects
                # the unknown scaffold_name (``dynamic._load_source_project_scaffold``)
                # and fails every import. Force it from the backend default.
                default_kind = self._candidate_extra_defaults().get("kind")
                if default_kind:
                    raw["kind"] = default_kind
        normalized_pending = json.dumps(
            {"candidates": proposed},
            indent=2,
            ensure_ascii=False,
        )
        self.pending_eval_path.write_text(normalized_pending, encoding="utf-8")
        (call_dir / "pending_eval.json").write_text(normalized_pending, encoding="utf-8")

        evaluated = self._evaluate_proposed(iteration, proposed, examples)
        best_ids = self._quality_frontier_ids(existing_candidates + evaluated)
        write_post_eval_artifacts(
            run_dir=self.run_dir,
            call_dir=call_dir,
            iteration=iteration,
            candidates=evaluated,
            frontier_ids=best_ids,
        )
        self.trace_harness.record_iteration(
            iteration=iteration,
            candidates=evaluated,
            patch_base=selected_base_iter,
            budget=budget,
            selection_policy=policy_name,
            proposer_call_dir=str(call_dir),
        )
        self.run_store.record_eval(iteration, evaluated)
        if evaluated:
            self.run_store.commit_iteration(iteration)
        self._refresh_run_store(iteration)
        self._refresh_run_indexes(existing_candidates + evaluated)
        self._score_prediction_feedback(
            iteration, evaluated, workspace_dir, existing_candidates
        )
        return evaluated

    def _build_progressive_workspace(
        self,
        *,
        iteration: int,
        budget: str,
        existing_candidates: list[CandidateResult],
        call_dir: Path,
        reference_iterations_override: tuple[int, ...] | None = None,
        base_iter: int | None = None,
    ) -> tuple[Path, tuple[int, ...]]:
        call_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir = call_dir / "workspace"
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        workspace_generated_dir = workspace_dir / "generated"
        workspace_generated_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_package_dirs(workspace_generated_dir, root=workspace_generated_dir)

        if reference_iterations_override is not None:
            # Caller-supplied refs are authoritative.
            reference_iterations = reference_iterations_override
        else:
            reference_iterations = self._reference_iterations_for_budget(
                budget,
                iteration=iteration,
                candidates=existing_candidates,
            )
            if base_iter is not None:
                # No override → strip base out of default refs.  The patch
                # base is already materialized inside `project_source/`, so
                # leaving it in refs would duplicate the same candidate as
                # both base and reference.
                reference_iterations = tuple(
                    item for item in reference_iterations if item != base_iter
                )
        assignment = {
            "iteration": iteration,
            "target_system": self.config.progressive_target_system,
            "budget": budget,
            "reference_iterations": list(reference_iterations),
            "generated_dir": str(workspace_generated_dir),
            "source_snapshot_dir": str(workspace_dir / "source_snapshot"),
            "pending_eval_path": str(workspace_dir / "pending_eval.json"),
            "base_iter": base_iter,
        }
        for dest in (call_dir / "assignment.json", workspace_dir / "assignment.json"):
            dest.write_text(json.dumps(assignment, indent=2, ensure_ascii=False), encoding="utf-8")

        if self._summaries_in_workspace_enabled():
            self._copy_workspace_summaries(workspace_dir / "summaries")
        self._copy_workspace_traces(workspace_dir / "traces")
        self._copy_reference_iterations(
            workspace_dir / "reference_iterations",
            reference_iterations=reference_iterations,
        )
        self._build_source_snapshot_workspace(
            iteration=iteration,
            source_family=self.config.progressive_target_system,
            call_dir=call_dir,
            target_system=self.config.progressive_target_system,
            snapshot_root=workspace_dir / "source_snapshot",
            generated_dir=workspace_generated_dir,
            base_iter=base_iter,
        )
        self._write_workspace_manifest(
            workspace_dir,
            call_dir=call_dir,
            assignment=assignment,
        )
        if self.config.selection_policy == "self":
            self._write_self_select_manifest(
                workspace_dir,
                existing_candidates,
                iteration=iteration,
                default_base_iter=base_iter,
                reference_iterations=tuple(reference_iterations),
            )
        self._write_access_policy(
            workspace_dir,
            source_snapshot_dir=workspace_dir / "source_snapshot",
            generated_dir=workspace_generated_dir,
            pending_eval_path=workspace_dir / "pending_eval.json",
        )
        self._copy_workspace_state(workspace_dir / "state.md")
        self._write_runtime_config(workspace_dir)
        self._sync_calibration_into_workspace(workspace_dir, iteration)
        self._prepare_workspace_run_store(iteration)
        self._deploy_mcp_server_assets(workspace_dir)
        self._write_proposer_agent_config(workspace_dir)
        self._deploy_proposer_skill(workspace_dir)
        return workspace_dir, reference_iterations

    def _uses_codex_proposer(self) -> bool:
        return self.config.proposer_agent.strip().lower() == "codex"

    def _codex_mcp_servers(self, workspace_dir: Path) -> dict[str, dict[str, Any]]:
        """Build the per-invocation MCP server spec for Codex.

        Returns ``{}`` when the runstore-tools surface is disabled (the
        ablation that hides the trace-harness section also disables the
        runstore tools). Mirrors ``_write_proposer_agent_config``
        on the Claude path, but emits a Python-dict spec that the runner
        translates into ``-c mcp_servers.runstore-tools.*`` overrides.

        Codex spawns MCP server subprocesses with the codex session's
        cwd (the workspace) as their working directory. RUNSTORE_DB and
        PYTHONPATH come out of ``_runstore_mcp_server_env`` as relative
        paths anchored at the project root, so we resolve them to
        absolute here — otherwise the MCP server would try to open
        ``<workspace>/runs/<run>/runstore.db`` and fail.
        """

        if not self.config.proposer_show_trace_harness_section:
            return {}
        runstore_env = dict(self._runstore_mcp_server_env(workspace_dir))
        for key in ("RUNSTORE_DB", "PYTHONPATH"):
            value = runstore_env.get(key)
            if value:
                runstore_env[key] = str(Path(value).resolve(strict=False))
        traces_env = dict(self._traces_mcp_server_env(workspace_dir))
        for key in ("TRACE_DB", "PYTHONPATH"):
            value = traces_env.get(key)
            if value:
                traces_env[key] = str(Path(value).resolve(strict=False))
        command = self._mcp_python_command()
        return {
            "runstore-tools": {
                "command": command,
                "args": ["-m", "worldcalib.run_store_mcp_server"],
                "env": runstore_env,
            },
            "worldcalib-traces": {
                "command": command,
                "args": ["-m", "worldcalib.traces.mcp_server"],
                "env": traces_env,
            },
        }

    def _uses_claude_subagent_proposer(self) -> bool:
        """Whether the proposer runs through the Claude Code CLI.

        For a Claude proposer the self-contained benchmark skill is
        delivered via ``--append-system-prompt``; for a Codex proposer
        it is written into ``<workspace>/AGENTS.md``.
        """

        return self.config.proposer_agent.strip().lower() == "claude"

    def _proposer_skill_mode(self) -> str:
        """Return the evidence-workflow mode for the proposer skill.

        Two independent axes: ``--organized`` selects the organized
        interface, and the summary axis (``_summaries_in_workspace_enabled``)
        selects whether the upstream summary files are exposed.
        """

        if not self.config.organized:
            return "default"
        if not self.config.organized_state_md:
            return "organized-no-state"
        if self._summaries_in_workspace_enabled():
            return "organized-summaries"
        return "organized"

    def _proposer_skill_key(self) -> str:
        """Return the benchmark skill key for this run.

        The two proposer variants route to a ``<benchmark>_<variant>`` skill:
        ``calib`` (self-distill WMC + self-graded per-task prediction) and
        ``nowmc`` (pure-default ablation, no calibration protocol). It is an
        error to request a variant for a benchmark that has no matching skill,
        so a misconfiguration fails loudly.
        """

        from worldcalib.prompts import benchmark_skill_name, proposer_skill_path

        key = benchmark_skill_name(
            benchmark_name=self._benchmark_prompt_name(),
            target_system=self.config.progressive_target_system,
        )
        suffix = self.config.proposer_variant
        if suffix not in ("calib", "nowmc"):
            raise ValueError(
                f"unknown proposer_variant={suffix!r} (expected 'calib' or 'nowmc')"
            )
        variant_key = f"{key}_{suffix}"
        if not proposer_skill_path(variant_key).exists():
            raise ValueError(
                f"proposer_variant='{suffix}' requested but no skill "
                f"exists at skills/{variant_key}/SKILL.md"
            )
        return variant_key

    def _resolve_proposer_skill(self) -> str:
        """Return the resolved per-benchmark proposer skill text.

        The skill is the proposer's full self-contained contract for
        this benchmark, with the active evidence-workflow mode block
        kept. It is delivered through the system-prompt channel.
        """

        from worldcalib.prompts import load_proposer_skill

        return load_proposer_skill(
            self._proposer_skill_key(), self._proposer_skill_mode()
        )

    def _deploy_proposer_skill(
        self, workspace_dir: Path, skill_text: str | None = None
    ) -> None:
        """Deploy the resolved per-benchmark proposer skill into the workspace.

        The skill is the proposer's full self-contained contract — role,
        objective, search space, workflow, quality gate, and
        ``pending_eval.json`` conventions — for this benchmark.

          - Codex proposer: the skill is written to ``<workspace>/AGENTS.md``,
            which Codex auto-loads at session start.
          - Claude proposer: the skill is delivered at invocation time via
            ``--append-system-prompt``; an audit copy is written to
            ``<workspace>/PROPOSER_SKILL.md``.

        No-op when the proposer agent is neither Codex nor Claude.
        """

        text = skill_text if skill_text is not None else self._resolve_proposer_skill()
        if self._uses_codex_proposer():
            self._deploy_codex_agents_md(workspace_dir, text)
            return
        if not self._uses_claude_subagent_proposer():
            return
        (workspace_dir / "PROPOSER_SKILL.md").write_text(text, encoding="utf-8")

    def _deploy_codex_agents_md(self, workspace_dir: Path, skill_text: str) -> None:
        """Write the Codex-facing ``<workspace>/AGENTS.md``.

        Codex auto-loads ``AGENTS.md`` at the session cwd and prepends it
        to its system prompt. We write the resolved per-benchmark proposer
        skill — the same contract the Claude path delivers via
        ``--append-system-prompt``.
        """

        body = (
            "# Codex proposer — auto-loaded contract\n\n"
            "Codex loads this file at session start. It is the proposer's "
            "self-contained skill for this benchmark: role, objective, "
            "search space, workflow, quality gate, and pending_eval.json "
            "conventions. Treat it as binding for this session.\n\n"
            "---\n\n"
            f"{skill_text.rstrip()}\n"
        )
        (workspace_dir / "AGENTS.md").write_text(body, encoding="utf-8")

    def _write_proposer_agent_config(self, workspace_dir: Path) -> None:
        """Register proposer-facing MCP servers in Claude settings.

        Writes ``<workspace>/.claude/settings.local.json`` with an
        ``mcpServers`` entry. Skipped when the trace-harness section is
        suppressed; in that ablation the proposer gets no historical
        query tools.

        No-op when the Codex proposer is selected: Codex has no
        per-workspace MCP config file; the runstore-tools server is
        injected at exec time via ``-c mcp_servers.runstore-tools.*``
        flags from :meth:`_codex_mcp_servers`.
        """

        if self._uses_codex_proposer():
            return
        if not self.config.proposer_show_trace_harness_section:
            return
        runstore_env = self._runstore_mcp_server_env(workspace_dir)
        traces_env = self._traces_mcp_server_env(workspace_dir)
        command = self._mcp_python_command()
        self._write_claude_settings(
            workspace_dir,
            servers={
                "runstore-tools": {
                    "command": command,
                    "args": ["-m", "worldcalib.run_store_mcp_server"],
                    "env": runstore_env,
                },
                "worldcalib-traces": {
                    "command": command,
                    "args": ["-m", "worldcalib.traces.mcp_server"],
                    "env": traces_env,
                },
            },
        )

    def _traces_mcp_server_env(self, workspace_dir: Path) -> dict[str, str]:
        """Env for the ``worldcalib-traces`` MCP server (trace_similar etc.).

        ``TRACE_DB`` points at the workspace-visible copy of the run's
        ``traces/index.db`` (mirrored by :meth:`_copy_workspace_traces`).
        OpenAI-compatible embedding credentials are forwarded explicitly
        so they survive ``_codex_env`` stripping ``OPENAI_API_KEY`` from
        the Codex CLI's own environment.
        """

        runstore_db = (
            Path("/runstore/runstore.db")
            if self.config.proposer_sandbox.strip().lower() == "docker"
            else self.run_store.db_path
        )
        env: dict[str, str] = {
            "TRACE_DB": str(self._workspace_visible_path(workspace_dir, "traces/index.db")),
            # trace_similar joins proposal_outcomes here for a deterministic,
            # parent-relative passrate_delta per neighbour (the proposer must
            # not hand-compute the base rate).
            "RUNSTORE_DB": str(runstore_db),
            "PYTHONPATH": str(self._mcp_pythonpath(workspace_dir)),
        }
        for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "DIFF_EMBEDDING_MODEL"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    def _runstore_mcp_server_env(self, workspace_dir: Path) -> dict[str, str]:
        runstore_db = (
            Path("/runstore/runstore.db")
            if self.config.proposer_sandbox.strip().lower() == "docker"
            else self.run_store.db_path
        )
        return {
            "RUNSTORE_DB": str(runstore_db),
            "PYTHONPATH": str(self._mcp_pythonpath(workspace_dir)),
        }

    def _mcp_python_command(self) -> str:
        if self.config.proposer_sandbox.strip().lower() == "docker":
            return "python"
        return sys.executable

    def _mcp_pythonpath(self, workspace_dir: Path) -> Path:
        return self._workspace_visible_path(workspace_dir, ".worldcalib_mcp_src")

    def _workspace_visible_path(self, workspace_dir: Path, rel: str) -> Path:
        if self.config.proposer_sandbox.strip().lower() == "docker":
            return Path(self.config.proposer_docker_workspace or "/workspace") / rel
        return workspace_dir / rel

    def _write_claude_settings(
        self,
        workspace_dir: Path,
        *,
        servers: dict[str, dict[str, Any]],
    ) -> None:
        """Write the workspace MCP server configuration.

        Current Claude Code loads project-scoped MCP servers from
        ``<workspace>/.mcp.json``.  Keep writing the older
        ``.claude/settings.local.json`` location as a compatibility copy for
        older CLIs, but the runner now passes ``--mcp-config .mcp.json``
        explicitly when the file exists.
        """

        settings_dir = workspace_dir / ".claude"
        settings_dir.mkdir(parents=True, exist_ok=True)
        config = {"mcpServers": servers}
        (workspace_dir / ".mcp.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (settings_dir / "settings.local.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _copy_workspace_traces(self, dest: Path) -> None:
        """Mirror run-level `traces/` into the proposer workspace.

        The proposer reads these files via the workspace mount; run-level
        paths are not directly accessible inside the sandbox, so we copy.
        """

        src = self.trace_harness.root
        if not src.exists():
            return
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    def _copy_workspace_run_store(self, dest: Path) -> None:
        src = self.run_store.db_path
        if src.exists():
            shutil.copy2(src, dest)

    def _prepare_workspace_run_store(self, iteration: int) -> None:
        self._refresh_run_store(iteration)

    def _deploy_mcp_server_assets(self, workspace_dir: Path) -> None:
        src_pkg = self.project_root / "src" / "worldcalib"
        dest_pkg = workspace_dir / ".worldcalib_mcp_src" / "worldcalib"
        if dest_pkg.exists():
            shutil.rmtree(dest_pkg)
        shutil.copytree(
            src_pkg,
            dest_pkg,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    def _write_state_md(
        self,
        *,
        iteration: int,
        as_of_iteration: int,
        base_iteration: int | None,
    ) -> None:
        state_md = self.run_store.render_state_md(
            iteration=iteration,
            as_of_iteration=as_of_iteration,
            benchmark=self.workspace_spec.benchmark,
            base_iteration=base_iteration,
        )
        self.run_store.record_state_snapshot(iteration, state_md)
        (self.run_dir / "state.md").write_text(state_md, encoding="utf-8")

    def _copy_workspace_state(self, dest: Path) -> None:
        if not self.config.organized or not self.config.organized_state_md:
            return
        src = self.run_dir / "state.md"
        if src.exists():
            shutil.copy2(src, dest)

    def _write_runtime_config(self, workspace_dir: Path) -> None:
        """Drop ground-truth runtime config into the proposer's cwd.

        Without this file the proposer must infer the target model from
        ``src/worldcalib/model.py`` defaults (``DEFAULT_MODEL``,
        ``enable_thinking``, ``max_tokens=256``). Those defaults are
        Qwen3-flavored and are overridden by the launcher at runtime, so
        proposer inference based on them is systematically wrong — observed
        as the "Qwen3 hidden thinking" red herring in early WMC runs.
        """

        cfg = self.config
        lines = [
            "# Runtime config (ground truth — read before any model-family inference)",
            "",
            f"- target_model: `{cfg.model}`",
            f"- target_base_url: `{cfg.base_url}`",
            f"- target_timeout_s: {cfg.eval_timeout_s}",
            "",
            "Notes for the proposer:",
            "- `src/worldcalib/model.py` `DEFAULT_MODEL` / `enable_thinking` / `max_tokens=256` are file-level defaults; the launcher overrides `model` and `base_url` via CLI at runtime. **Use the values above, not the file defaults, when reasoning about target behavior.**",
            "- `max_tokens=256` IS still the per-call cap unless a scaffold overrides it. Tasks with `completion_tokens == 256` and empty `prediction` mean the model hit the cap, NOT necessarily that any specific model family's hidden-thinking ate the budget.",
            "- Do not name a specific model family (Qwen / Claude / GPT / etc.) in your distill unless that name appears verbatim in `target_model` above.",
        ]
        (workspace_dir / "runtime_config.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    # ---- calib variant: hidden mechanical prediction telemetry --------------

    def _calib_result_path(self, candidate: CandidateResult) -> Path | None:
        """Resolve a candidate's result json to an absolute path."""
        rp = getattr(candidate, "result_path", "") or ""
        if rp:
            p = Path(rp)
            if not p.is_absolute():
                p = (self.run_dir.parent.parent / rp) if rp.startswith("runs/") else (self.run_dir / rp)
            if p.is_file():
                return p
        cid = getattr(candidate, "candidate_id", "") or ""
        hits = sorted((self.run_dir / "candidate_results").glob(f"*{cid}*.json")) if cid else []
        return hits[0] if hits else None

    def _calib_base_breakdown(
        self, parsed, existing_candidates: list[CandidateResult]
    ) -> dict:
        """score_breakdown of the parent the proposer's prediction is measured against.

        Resolution (NOT the current best — that would bias every prediction
        toward the same reference and is unrelated to what the proposer actually
        built on):
          1. declared ``iter_<N>`` → that iter's candidate_results.
          2. declared ``clean`` OR missing → the iter-0 seed baseline. Under the
             default policy the editable source is re-baselined from the clean
             snapshot every iter, so an undeclared/clean candidate genuinely
             started from the baseline — its true per-type delta is vs iter 0.
        """
        from worldcalib.prediction_feedback import load_score_breakdown

        if getattr(parsed, "base_iter", None) is not None:
            hits = sorted(
                (self.run_dir / "candidate_results").glob(
                    f"iter{parsed.base_iter:03d}*.json"
                )
            )
            if hits:
                return load_score_breakdown(hits[0])
        # clean / missing → iter-0 seed baseline (candidate_id without an
        # "iter" prefix is the seed scaffold loaded from the baseline dir).
        for c in existing_candidates:
            cid = getattr(c, "candidate_id", "") or ""
            if not cid.startswith("iter"):
                p = self._calib_result_path(c)
                if p:
                    return load_score_breakdown(p)
        if self.config.baseline_dir:
            bdir = Path(self.config.baseline_dir) / "candidate_results"
            hits = sorted(bdir.glob("*.json")) if bdir.exists() else []
            if hits:
                return load_score_breakdown(hits[0])
        return {}

    def _calib_base_task_outcomes(
        self, parsed, existing_candidates: list[CandidateResult]
    ) -> dict:
        """Per-task ``{task_id: passed}`` of the base the prediction is measured
        against. Same base resolution as :meth:`_calib_base_breakdown` (declared
        iter_<N> → that iter; clean/missing → iter-0 seed baseline), but returns
        the per-task outcomes the per-task flip grader needs."""
        from worldcalib.prediction_feedback import load_task_outcomes

        if getattr(parsed, "base_iter", None) is not None:
            hits = sorted(
                (self.run_dir / "candidate_results").glob(
                    f"iter{parsed.base_iter:03d}*.json"
                )
            )
            if hits:
                return load_task_outcomes(hits[0])
        for c in existing_candidates:
            cid = getattr(c, "candidate_id", "") or ""
            if not cid.startswith("iter"):
                p = self._calib_result_path(c)
                if p:
                    return load_task_outcomes(p)
        if self.config.baseline_dir:
            bdir = Path(self.config.baseline_dir) / "candidate_results"
            hits = sorted(bdir.glob("*.json")) if bdir.exists() else []
            if hits:
                return load_task_outcomes(hits[0])
        return {}

    def _score_prediction_feedback(
        self,
        iteration: int,
        evaluated: list[CandidateResult],
        workspace_dir: Path,
        existing_candidates: list[CandidateResult],
    ) -> None:
        """calib variant: score this iter's prediction vs the real outcome.

        Runs AFTER eval. HIDDEN TELEMETRY ONLY — the self-distill protocol means
        the proposer grades its own prediction next iter; nothing computed here
        is ever staged into a proposer workspace. We mechanically compare the
        prediction's per-task flips against the real outcome
        (:mod:`worldcalib.prediction_feedback`, pure code, no LLM), append a row
        to the run-level ``prediction_grades.md`` ledger, and log a
        ``prediction_score`` event that forms the offline calibration learning
        curve. Best-effort; never breaks the loop.
        """
        if self.config.proposer_variant != "calib" or not evaluated:
            return
        try:
            from worldcalib.prediction_feedback import (
                evaluate_prediction,
                load_task_outcomes,
                parse_prediction,
            )

            pred_path = workspace_dir / "prediction.md"
            if not pred_path.is_file():
                return
            pred_text = pred_path.read_text(encoding="utf-8")
            parsed = parse_prediction(pred_text)
            base_iter = parsed.base_iter
            cand_path = self._calib_result_path(evaluated[0])
            cand_outcomes = load_task_outcomes(cand_path) if cand_path else {}
            base_outcomes = self._calib_base_task_outcomes(parsed, existing_candidates)
            # Per-task flip grading: predicted task_id flips vs real flips
            # (candidate tasks[] vs the declared base's tasks[]).
            metrics = evaluate_prediction(pred_text, cand_outcomes, base_outcomes)

            ledger_path = self.run_dir / "prediction_grades.md"
            if not ledger_path.exists():
                ledger_path.write_text(
                    "# Prediction telemetry ledger (mechanical, offline-only — "
                    "never shown to the proposer)\n\n"
                    "| iter | flip_hit | n_pred | blind_spots | "
                    "net_real | base |\n"
                    "|---|---|---|---|---|---|\n",
                    encoding="utf-8",
                )
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"| {iteration} | "
                    f"{metrics.get('flip_hit_rate')} | "
                    f"{metrics.get('n_predicted_flips')} | "
                    f"{metrics.get('n_blind_spot_regressions')} | "
                    f"{metrics.get('net_real_flips')} | "
                    f"{parsed.base_raw or 'n/a'} |\n"
                )

            self._append_event(
                {
                    "iteration": iteration,
                    "event": "prediction_score",
                    "flip_hit_rate": metrics.get("flip_hit_rate"),
                    "n_predicted_flips": metrics.get("n_predicted_flips"),
                    "n_flip_hits": metrics.get("n_flip_hits"),
                    "n_blind_spot_regressions": metrics.get("n_blind_spot_regressions"),
                    "net_real_flips": metrics.get("net_real_flips"),
                    "base_iter": base_iter,
                    "base_raw": parsed.base_raw,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self._append_event(
                {"event": "prediction_score_failed", "iteration": iteration,
                 "error": repr(exc)}
            )

    def _sync_calibration_into_workspace(
        self, workspace_dir: Path, iteration: int
    ) -> None:
        """Copy the run-level calibration into the proposer's cwd, plus the
        previous iter's prediction as ``prev_prediction.md``. Makes
        ``world_model_calibration.md`` and ``prev_prediction.md`` available
        at workspace-relative paths so SKILL.md doesn't depend on knowing
        the docker mount layout.

        Hard no-op for the ``nowmc`` variant: the pure-default ablation carries
        no calibration protocol at all (no prose file, no prediction, no
        world model), so nothing is staged into the workspace.
        """

        if self.config.proposer_variant == "nowmc":
            return

        src = self.run_dir / "world_model_calibration.md"
        if src.exists():
            shutil.copy2(src, workspace_dir / "world_model_calibration.md")
        if iteration > 0:
            prev = (
                self._iteration_dir(iteration - 1) / "workspace" / "prediction.md"
            )
            if prev.exists():
                shutil.copy2(prev, workspace_dir / "prev_prediction.md")

    def _sync_calibration_back_from_workspace(self, cwd: Path | None) -> None:
        """If the proposer appended to its workspace-local calibration copy,
        promote that back to the run-level file. Idempotent if unchanged.

        Hard no-op for the ``nowmc`` ablation: it carries no prose calibration
        file, so nothing is ever promoted back even if a stray file appears.
        """

        if self.config.proposer_variant == "nowmc":
            return
        if cwd is None:
            return
        src = Path(cwd) / "world_model_calibration.md"
        if not src.exists():
            return
        dest = self.run_dir / "world_model_calibration.md"
        shutil.copy2(src, dest)

    def _refresh_run_store(self, iteration: int) -> None:
        """Best-effort RunStore trace/artifact refresh.

        The incremental RunStore writes are the source of truth; a
        trace/artifact import issue should be visible but must not burn an
        optimization iteration.
        """

        try:
            self.run_store.refresh(iteration=iteration)
        except Exception as exc:  # noqa: BLE001 - diagnostic sidecar only
            self.run_dir.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "iteration": int(iteration),
                "error": str(exc),
            }
            with (self.run_dir / "runstore_refresh_errors.jsonl").open(
                "a",
                encoding="utf-8",
            ) as fh:
                fh.write(json.dumps(row, ensure_ascii=False))
                fh.write("\n")

    def _copy_workspace_summaries(self, summaries_dir: Path) -> None:
        # Only the two upstream meta-harness summary files are exposed to the
        # proposer: the full event history and the current quality frontier.
        # The other run-level digests (candidate_score_table, retrieval
        # diagnostics, iteration_index, diff_summary) are still written under
        # the run directory but are not copied into the proposer workspace.
        summaries_dir.mkdir(parents=True, exist_ok=True)
        summary_files = (
            (self.summary_path, "evolution_summary.jsonl", ""),
            (self.frontier_path, "best_candidates.json", "[]\n"),
        )
        for src, name, default_text in summary_files:
            dest = summaries_dir / name
            if src.exists():
                shutil.copy2(src, dest)
            else:
                dest.write_text(default_text, encoding="utf-8")

    def _summaries_in_workspace_enabled(self) -> bool:
        # Independent of --organized: governed solely by the summary axis.
        return self.config.summaries_in_workspace

    def _copy_reference_iterations(
        self,
        reference_dir: Path,
        *,
        reference_iterations: tuple[int, ...],
    ) -> None:
        reference_dir.mkdir(parents=True, exist_ok=True)
        for item in reference_iterations:
            src = self._iteration_dir(item)
            if not src.exists():
                continue
            self._copy_iteration_bundle(
                src,
                reference_dir / f"iter_{item:03d}",
            )

    def _write_workspace_manifest(
        self,
        workspace_dir: Path,
        *,
        call_dir: Path,
        assignment: dict[str, Any],
    ) -> None:
        manifest = {
            "workspace_dir": str(workspace_dir),
            "call_dir": str(call_dir),
            "assignment": assignment,
            "summaries_dir": str(workspace_dir / "summaries"),
            "reference_iterations_dir": str(workspace_dir / "reference_iterations"),
            "source_snapshot_dir": str(workspace_dir / "source_snapshot"),
            "generated_dir": str(workspace_dir / "generated"),
            "pending_eval_path": str(workspace_dir / "pending_eval.json"),
        }
        for dest in (
            workspace_dir / "workspace_manifest.json",
            call_dir / "workspace_manifest.json",
        ):
            dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_access_policy(
        self,
        workspace_dir: Path,
        *,
        source_snapshot_dir: Path,
        generated_dir: Path,
        pending_eval_path: Path,
    ) -> None:
        policy = {
            "read_roots": [str(workspace_dir)],
            "write_roots": [
                str(source_snapshot_dir / "candidate"),
                str(generated_dir),
            ],
            "write_files": [str(pending_eval_path)],
            "forbidden_roots": [
                str(self.project_root),
                str(self.run_dir),
                str(self.project_root / "references" / "vendor"),
                str(self.run_dir / "candidate_results"),
            ],
            "notes": [
                "The proposer workspace is self-contained.",
                (
                    "Do not read global runs, repo-root source, references/vendor, "
                    f"{self._raw_data_policy_name()}, or scoring helpers."
                ),
            ],
        }
        for dest in (
            workspace_dir / "access_policy.json",
            workspace_dir.parent / "access_policy.json",
        ):
            dest.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")

    def _archive_workspace_outputs(
        self,
        *,
        workspace_dir: Path,
        call_dir: Path,
        result: Any,
    ) -> None:
        self._sync_workspace_outputs(workspace_dir=workspace_dir, call_dir=call_dir)

        source_snapshot = workspace_dir / "source_snapshot"
        archived_snapshot = call_dir / "source_snapshot"
        if source_snapshot.exists():
            if archived_snapshot.exists():
                shutil.rmtree(archived_snapshot)
            shutil.copytree(
                source_snapshot,
                archived_snapshot,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

        for name in ("workspace_manifest.json", "access_policy.json"):
            self._copy_if_exists(workspace_dir / name, call_dir / name)

        agent_dir = call_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        tool_access = getattr(result, "tool_access", None)
        if isinstance(tool_access, dict):
            (agent_dir / "tool_access.json").write_text(
                json.dumps(tool_access, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        metrics = getattr(result, "metrics", None)
        if isinstance(metrics, dict):
            (agent_dir / "metrics.json").write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        self._write_source_snapshot_diff(call_dir)
        write_diff_digest(call_dir=call_dir)
        self._append_diff_summary(call_dir)

    def _write_source_snapshot_diff(self, call_dir: Path) -> None:
        pairs = self._source_snapshot_diff_pairs(call_dir)
        if not pairs:
            (call_dir / "diff.patch").write_text(
                "Source snapshot diff unavailable.\n",
                encoding="utf-8",
            )
            return
        chunks: list[str] = []
        for original, updated in pairs:
            cmd = ["git", "diff", "--no-index", "--", str(original), str(updated)]
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=str(self.project_root),
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                text = completed.stdout or completed.stderr or ""
            except Exception as exc:  # noqa: BLE001 - best-effort artifact
                text = f"Failed to capture source snapshot diff for {updated}: {exc}\n"
            if text:
                chunks.append(text.rstrip("\n"))
        (call_dir / "diff.patch").write_text(
            ("\n".join(chunks) + "\n") if chunks else "",
            encoding="utf-8",
        )

    def _source_snapshot_diff_pairs(self, call_dir: Path) -> list[tuple[Path, Path]]:
        candidate = call_dir / "source_snapshot" / "candidate"
        pairs = [
            (candidate / "original_project_source", candidate / "project_source"),
            (candidate / "original_upstream_source", candidate / "upstream_source"),
        ]
        return [(original, updated) for original, updated in pairs if original.exists() and updated.exists()]

    def _append_diff_summary(self, call_dir: Path) -> None:
        iteration = _iteration_from_dir_name(call_dir.name) or 0
        diff_path = call_dir / "diff.patch"
        text = diff_path.read_text(encoding="utf-8", errors="replace") if diff_path.exists() else ""
        stats = diff_stats(text)
        self.run_store.record_diff(iteration, text)
        self._refresh_run_store(iteration)
        row = {
            "iteration": iteration,
            "iteration_dir": str(call_dir),
            "diff_path": str(diff_path),
            "diff_digest_path": str(call_dir / "diff_digest.md"),
            "files_changed": stats["files_changed"],
            "insertions": stats["insertions"],
            "deletions": stats["deletions"],
        }
        rows: list[dict[str, Any]] = []
        if self.diff_summary_path.exists():
            for raw in self.diff_summary_path.read_text(encoding="utf-8").splitlines():
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and int(item.get("iteration") or -1) != iteration:
                    rows.append(item)
        rows.append(row)
        self.diff_summary_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
            encoding="utf-8",
        )

    def _load_examples(self) -> list[LocomoExample]:
        return self._load_examples_for_split(self.config.split, self.config.limit)

    def _load_examples_for_split(self, split: str, limit: int = 0) -> list[LocomoExample]:
        if not default_data_path().exists():
            prepare_locomo()
        examples = load_locomo_examples()
        selected = select_split(examples, split=split)
        if limit:
            selected = selected[:limit]
        return selected

    def _run_seed_frontier(self) -> dict[str, Any]:
        return run_initial_frontier(
            split=self.config.split,
            limit=self.config.limit,
            out_dir=self.run_dir,
            model=self.config.model,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout_s=self.config.eval_timeout_s,
            dry_run=self.config.dry_run,
            max_context_chars=self.config.max_context_chars,
            max_eval_workers=self.config.max_eval_workers,
            pareto_quality_threshold=self.config.pareto_quality_threshold,
            scaffolds=self.config.scaffolds,
            scaffold_extra=self.config.scaffold_extra,
        )

    def _run_test_frontier(self, candidates: list[CandidateResult]) -> dict[str, Any]:
        full_frontier = self._quality_frontier(candidates)
        candidate_limit = max(0, int(self.config.test_frontier_candidate_limit or 0))
        frontier = full_frontier[:candidate_limit] if candidate_limit else full_frontier
        test_dir = self.run_dir / "test_frontier"
        specs_dir = test_dir / "candidate_specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        examples = self._load_examples_for_split(self.config.test_split, self.config.test_limit)
        runner = self._make_evaluation_runner(examples, out_dir=test_dir)

        rows: list[dict[str, Any]] = []
        test_results: list[CandidateResult] = []
        failures: list[dict[str, Any]] = []
        for candidate in frontier:
            spec = self._candidate_test_spec(candidate)
            spec_path = specs_dir / f"{spec['candidate_id']}.json"
            spec_path.write_text(
                json.dumps(spec, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                scaffold = load_candidate_scaffold(spec, project_root=self.project_root)
                config = ScaffoldConfig(
                    top_k=int(spec.get("top_k", 8)),
                    window=int(spec.get("window", 1)),
                    extra=dict(spec.get("extra") or {}),
                )
                result = runner.evaluate_scaffold(
                    scaffold=scaffold,
                    scaffold_name=str(spec.get("name") or candidate.scaffold_name),
                    config=config,
                    candidate_id=str(spec["candidate_id"]),
                )
            except Exception as exc:  # noqa: BLE001 - keep testing the rest of the frontier
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
                self._append_event(
                    {
                        "event": "test_frontier_candidate_failed",
                        **failure,
                    }
                )
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

    def _candidate_test_spec(self, candidate: CandidateResult) -> dict[str, Any]:
        config = candidate.config if isinstance(candidate.config, dict) else {}
        extra = self._candidate_extra(candidate)
        top_k, _ = _single_top_k(config.get("top_k", 8))
        spec: dict[str, Any] = {
            "name": candidate.scaffold_name,
            "candidate_id": self._test_candidate_id(candidate.candidate_id),
            "original_candidate_id": candidate.candidate_id,
            "top_k": top_k,
            "window": int(config.get("window", 1)),
            "extra": extra,
        }
        for key in (
            "build_tag",
            "candidate_root",
            "class",
            "factory",
            "generated_dir",
            "module",
            "module_path",
            "project_source_path",
            "source_project_path",
            "memomemo_source_path",
        ):
            if key in extra:
                spec[key] = extra[key]

        has_source_project = any(
            spec.get(key)
            for key in ("source_project_path", "project_source_path", "memomemo_source_path")
        )
        has_dynamic_module = bool(spec.get("module") or spec.get("module_path"))
        if has_source_project:
            spec["scaffold_name"] = self._source_scaffold_name(candidate)
        elif not has_dynamic_module:
            spec["scaffold_name"] = str(extra.get("scaffold_name") or candidate.scaffold_name)
        return spec

    def _source_scaffold_name(self, candidate: CandidateResult) -> str:
        extra = self._candidate_extra(candidate)
        explicit = str(extra.get("scaffold_name") or "").strip()
        if explicit:
            return explicit
        return {
            "memgpt": "memgpt_source",
        }.get(self._infer_source_family(candidate), candidate.scaffold_name)

    def _test_candidate_id(self, candidate_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate_id).strip("._-")
        return f"test_{safe or 'candidate'}"

    def _benchmark_prompt_name(self) -> str:
        return "LOCOMO conversational-memory QA"

    def _raw_data_policy_name(self) -> str:
        return "raw LOCOMO data"

    def _run_proposer_agent(
        self,
        prompt: str,
        *,
        log_dir: Path,
        name: str,
        cwd: Path | None = None,
        skill_text: str | None = None,
        sync_calibration_back: bool = True,
        timeout_s: int | None = None,
    ) -> Any:
        agent = self.config.proposer_agent.strip().lower()
        proposer_cwd = cwd or self.project_root
        kwargs: dict[str, Any] = dict(
            cwd=proposer_cwd,
            log_dir=log_dir,
            name=name,
            timeout_s=timeout_s if timeout_s is not None else self.config.propose_timeout_s,
            sandbox=self._proposer_sandbox_config(),
            # On a docker timeout, kill the orphaned container instead of
            # leaking it; give the in-flight candidate a short grace to land.
            salvage_ready_path=proposer_cwd / "pending_eval.json",
            salvage_grace_s=self.config.propose_salvage_grace_s,
            model=self.config.claude_model,
            effort=self.config.claude_effort,
            claude_base_url=self.config.claude_base_url,
            claude_auth_token=self.config.claude_auth_token,
            claude_native_auth=self.config.claude_native_auth,
            codex_model=self.config.codex_model,
            codex_reasoning_effort=self.config.codex_reasoning_effort,
            codex_home=self.config.codex_home or None,
        )
        # The proposer's self-contained benchmark skill is delivered
        # through the system-prompt channel via --append-system-prompt,
        # so the role / identity / contract text never enters the user
        # message. (Codex receives the same skill from <workspace>/AGENTS.md,
        # written by _deploy_proposer_skill.)
        if self._uses_claude_subagent_proposer() and (
            name == "proposer" or skill_text is not None
        ):
            kwargs["claude_append_system_prompt"] = (
                skill_text if skill_text is not None else self._resolve_proposer_skill()
            )
        # Codex has no per-workspace MCP config flag like Claude's
        # --mcp-config: we inject the runstore-tools server via
        # -c mcp_servers.runstore-tools.* on every exec instead.
        if self._uses_codex_proposer() and cwd is not None:
            kwargs["codex_mcp_servers"] = self._codex_mcp_servers(cwd)

        retries = 0
        while True:
            # Re-sync the docker proposer's staged Claude OAuth credentials
            # with the host's before every attempt. Crucial after a long
            # rate-limit wait: the per-run STAGE_HOME copy made at launch
            # time would otherwise have expired (→ 401 cascade) while we
            # slept out the 429 window.
            self._refresh_native_auth_credentials()
            result = run_code_agent_prompt(prompt, agent=agent, **kwargs)
            # Promote any append the proposer made to its workspace-local
            # calibration copy back to the run-level file. Safe to do per
            # attempt — copy is idempotent if the file is unchanged. Skipped in
            # fan-out mode, where K parallel proposers each hold their own copy
            # and only the selected winner's world model is promoted back.
            if sync_calibration_back:
                self._sync_calibration_back_from_workspace(kwargs.get("cwd"))
            if not (
                self.config.wait_on_rate_limit
                and getattr(result, "rate_limited", False)
                and retries < self.config.rate_limit_max_retries
            ):
                return result
            retries += 1
            self._wait_for_rate_limit_reset(
                result, retry=retries, name=name, log_dir=log_dir
            )

    def _wait_for_rate_limit_reset(
        self, result: Any, *, retry: int, name: str, log_dir: Path
    ) -> None:
        """Sleep until an Anthropic usage-limit window resets, logging a
        ``proposer_rate_limited`` event and periodic progress.

        Called from :meth:`_run_proposer_agent` before retrying the same
        invocation, so a 429 does not consume the iteration."""

        now = time.time()
        resets_at = getattr(result, "rate_limit_resets_at", None)
        if isinstance(resets_at, (int, float)) and resets_at > now:
            wait_s = (resets_at - now) + self.config.rate_limit_buffer_s
        else:
            wait_s = float(self.config.rate_limit_default_wait_s)
        wait_s = max(1.0, min(wait_s, float(self.config.rate_limit_max_wait_s)))
        resume_at = now + wait_s
        self._append_event(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event": "proposer_rate_limited",
                "name": name,
                "log_dir": str(log_dir),
                "retry": retry,
                "max_retries": self.config.rate_limit_max_retries,
                "resets_at": resets_at,
                "wait_s": round(wait_s, 1),
                "resume_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.localtime(resume_at)
                ),
            }
        )
        poll = max(1, int(self.config.rate_limit_poll_log_s))
        print(
            f"[{self.config.run_id}] {name}: usage limit hit "
            f"(retry {retry}/{self.config.rate_limit_max_retries}); "
            f"waiting ~{wait_s / 60:.1f} min, resuming at "
            f"{time.strftime('%H:%M:%S', time.localtime(resume_at))}",
            flush=True,
        )
        while True:
            remaining = resume_at - time.time()
            if remaining <= 0:
                break
            chunk = min(float(poll), remaining)
            time.sleep(chunk)
            remaining = resume_at - time.time()
            if remaining > 0:
                print(
                    f"[{self.config.run_id}] {name}: still rate-limited, "
                    f"~{remaining / 60:.1f} min left",
                    flush=True,
                )

    def _native_auth_stage_home(self) -> Path | None:
        """Locate the host directory bind-mounted at the docker proposer's
        ``$HOME`` under ``--claude-native-auth``.

        That directory holds the per-run copy of ``~/.claude.json`` +
        ``~/.claude/.credentials.json`` (see the launch script's
        ``prepare_proposer_home``); identifying it lets us keep the staged
        OAuth credentials in sync with the host's. Returns ``None`` when
        native auth is off, the proposer is not sandboxed in docker, or no
        mount targets the container ``$HOME``."""

        if not self.config.claude_native_auth:
            return None
        if self.config.proposer_sandbox.strip().lower() != "docker":
            return None
        home = (self.config.proposer_docker_home or "").rstrip("/")
        if not home:
            return None
        found: Path | None = None
        for spec in self.config.proposer_docker_mount:
            parts = str(spec).split(":")
            if len(parts) < 2 or not parts[0]:
                continue
            if parts[1].rstrip("/") == home:
                found = Path(parts[0])  # last mount wins, matching docker
        return found

    def _refresh_native_auth_credentials(self) -> None:
        """Copy the host's current ``~/.claude/.credentials.json`` into the
        docker proposer's staged ``$HOME`` so a token the host CLI has since
        rotated/refreshed is the one the container sees.

        No-op unless ``--claude-native-auth`` + a docker proposer with a
        mount at the container ``$HOME``. Best-effort: a transient read/copy
        failure is logged and swallowed (the proposer call then fails/retries
        exactly as it would have without this sync)."""

        stage = self._native_auth_stage_home()
        if stage is None:
            return
        host_creds = Path.home() / ".claude" / ".credentials.json"
        if not host_creds.is_file():
            return
        dst = stage / ".claude" / ".credentials.json"
        try:
            if dst.is_file() and dst.read_bytes() == host_creds.read_bytes():
                return
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(host_creds, dst)
            dst.chmod(0o600)
        except OSError as exc:
            self._append_event(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "event": "native_auth_refresh_failed",
                    "stage_home": str(stage),
                    "error": repr(exc),
                }
            )

    def _proposer_sandbox_config(self) -> ProposerSandboxConfig | None:
        kind = self.config.proposer_sandbox.strip().lower()
        if kind == "none":
            return None
        if kind != "docker":
            raise ValueError(f"unsupported proposer sandbox: {self.config.proposer_sandbox!r}")
        docker_env = _dedupe_tuple(
            DEFAULT_DOCKER_ENV_VARS + self.config.proposer_docker_env
        )
        docker_mount = tuple(self.config.proposer_docker_mount)
        runstore_db = self.run_store.db_path.resolve(strict=False)
        if runstore_db.exists():
            docker_mount = (
                *docker_mount,
                f"{runstore_db}:/runstore/runstore.db:ro",
            )
        docker_mount = _dedupe_tuple(docker_mount)
        return ProposerSandboxConfig(
            kind="docker",
            docker_image=self._effective_proposer_docker_image(),
            docker_workspace=self.config.proposer_docker_workspace or "/workspace",
            docker_env_vars=docker_env,
            docker_mounts=docker_mount,
            docker_user=self.config.proposer_docker_user,
            docker_home=self.config.proposer_docker_home,
        )

    def _effective_proposer_docker_image(self) -> str:
        configured = self.config.proposer_docker_image.strip()
        if configured:
            return configured
        return DEFAULT_PROPOSER_DOCKER_IMAGE

    def _evaluate_proposed(
        self,
        iteration: int,
        proposed: list[dict[str, Any]],
        examples: list[LocomoExample],
    ) -> list[CandidateResult]:
        runner = self._make_evaluation_runner(examples)
        results: list[CandidateResult] = []
        for raw in proposed:
            if isinstance(raw, dict):
                raw = dict(raw)
                raw.setdefault("candidate_root", str(self.generated_dir))
            violations = self._candidate_code_policy_violations(raw)
            if violations:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_policy_rejected",
                        "candidate": raw,
                        "violations": violations,
                    }
                )
                continue
            try:
                scaffold = load_candidate_scaffold(raw, project_root=self.project_root)
            except Exception as exc:  # noqa: BLE001 - log and continue
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_import_failed",
                        "candidate": raw,
                        "error": str(exc),
                    }
                )
                continue

            top_k, top_k_adjusted = _single_top_k(raw.get("top_k", 8))
            if top_k_adjusted:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_top_k_adjusted",
                        "candidate": raw,
                        "evaluated_top_k": top_k,
                    }
                )
            extra = dict(raw.get("extra") or {})
            for key in (
                "build_tag",
                "candidate_root",
                "class",
                "cost_level",
                "factory",
                "generated_dir",
                "module",
                "module_path",
                "project_source_path",
                "scaffold_name",
                "source_base_dir",
                "source_family",
                "source_path",
                "source_project_path",
                "upstream_source_path",
                "memgpt_source_path",
                "optimization_target",
            ):
                if key in raw and key not in extra:
                    extra[key] = raw[key]
            for key, value in self._candidate_extra_defaults().items():
                extra.setdefault(key, value)
            config = ScaffoldConfig(
                top_k=top_k,
                window=int(raw.get("window", 1)),
                extra=extra,
            )
            candidate_name = str(raw.get("name") or scaffold.name)
            candidate_id = f"iter{iteration:03d}_{candidate_name}_top{top_k}"
            crash = self._dry_run_probe(
                scaffold=scaffold,
                scaffold_name=candidate_name,
                config=config,
                candidate_id=candidate_id,
                examples=examples,
            )
            if crash:
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_dry_run_rejected",
                        "candidate_id": candidate_id,
                        "reason": crash,
                    }
                )
                continue
            try:
                result = runner.evaluate_scaffold(
                    scaffold=scaffold,
                    scaffold_name=candidate_name,
                    config=config,
                    candidate_id=candidate_id,
                )
            except Exception as exc:  # noqa: BLE001 - log and continue
                self._append_event(
                    {
                        "iteration": iteration,
                        "event": "candidate_eval_failed",
                        "candidate": raw,
                        "candidate_id": candidate_id,
                        "error": str(exc),
                    }
                )
                continue
            results.append(result)
            self._append_summary(iteration=iteration, candidate=result, proposal=raw)
        return results

    def _probe_rejects_on_zero_completion_tokens(self) -> bool:
        """Whether the dry-run probe may reject a candidate for emitting zero
        completion tokens across all probe tasks.

        True when the eval backend reports per-task token usage (memory, tau2):
        zero completion tokens then genuinely signals a runtime crash. False for
        backends that hardcode 0 tokens (agentbench, whose agentrl client never
        surfaces usage) — there the heuristic would false-positive on every
        working candidate, so the probe falls back to the raised-exception
        signal only.
        """
        return True

    def _dry_run_probe(
        self,
        *,
        scaffold: Any,
        scaffold_name: str,
        config: Any,
        candidate_id: str,
        examples: list[LocomoExample],
    ) -> str | None:
        """Smoke-run the candidate on a few tasks before the full eval.

        Returns a crash reason string if the candidate is a runtime crash
        (raised while building/answering, or produced zero model output on
        every probe task — the signature of the iter_29 ``KeyError``), else
        None. Best-effort: a probe-infrastructure error does NOT reject the
        candidate (the full eval's own guard still applies); only a clear
        no-output / raised-exception signal does.
        """

        k = max(0, int(self.config.dry_run_probe_k))
        if k == 0 or not examples:
            return None
        import tempfile

        probe_examples = examples[:k]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                # Use the BACKEND-specific runner (memory / agentbench / tau2),
                # not a hardcoded generic EvaluationRunner: tau2 + agentbench
                # ignore config.model/base_url and drive their own eval clients,
                # so a generic runner would produce zero output on every probe
                # task and falsely reject every candidate (the locomo-era probe
                # only ever ran against the memory runner).
                probe = self._make_evaluation_runner(probe_examples, out_dir=Path(tmp))
                res = probe.evaluate_scaffold(
                    scaffold=scaffold,
                    scaffold_name=scaffold_name,
                    config=config,
                    candidate_id=candidate_id,
                )
        except Exception as exc:  # noqa: BLE001 — a raised eval IS the crash signal
            return f"scaffold raised during dry-run: {type(exc).__name__}: {exc}"
        if (
            res.count > 0
            and self._probe_rejects_on_zero_completion_tokens()
            and res.avg_completion_tokens == 0
        ):
            return (
                "dry-run produced zero model output on all "
                f"{res.count} probe tasks (likely runtime crash)"
            )
        return None

    def _make_evaluation_runner(
        self,
        examples: list[LocomoExample],
        *,
        out_dir: Path | None = None,
    ) -> EvaluationRunner:
        return EvaluationRunner(
            examples=examples,
            out_dir=out_dir or self.run_dir,
            model=self.config.model,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout_s=self.config.eval_timeout_s,
            dry_run=self.config.dry_run,
            max_context_chars=self.config.max_context_chars,
            max_eval_workers=self.config.max_eval_workers,
        )

    def _candidate_extra_defaults(self) -> dict[str, object]:
        return {}

    def _candidate_code_policy_violations(self, candidate: Any) -> list[dict[str, str]]:
        if not isinstance(candidate, dict):
            return []
        paths = self._candidate_policy_scan_paths(candidate)
        violations: list[dict[str, str]] = []
        forbidden = {
            "candidate_results": "runtime code must not read previous candidate results",
            "data/locomo": "runtime code must not read raw LOCOMO data",
            "data\\locomo": "runtime code must not read raw LOCOMO data",
            "locomo10.json": "runtime code must not read raw LOCOMO data",
            "data/longmemeval": "runtime code must not read raw LongMemEval data",
            "data\\longmemeval": "runtime code must not read raw LongMemEval data",
            "longmemeval_s_cleaned.json": "runtime code must not read raw LongMemEval data",
            "longmemeval_m_cleaned.json": "runtime code must not read raw LongMemEval data",
            "longmemeval_oracle.json": "runtime code must not read raw LongMemEval data",
            "score_prediction": "runtime code must not call OptiHarness scoring helpers",
            "worldcalib.metrics": "runtime code must not import OptiHarness scoring helpers",
            "load_locomo_examples": "runtime code must not load the full LOCOMO dataset",
            "load_longmemeval_examples": "runtime code must not load the full LongMemEval dataset",
        }
        source_project = self._candidate_source_project_root(candidate)
        original_source_project = (
            self._candidate_original_source_project_root(source_project)
            if source_project is not None
            else None
        )
        for path in paths:
            text = self._candidate_policy_scan_text(
                path,
                source_project=source_project,
                original_source_project=original_source_project,
            )
            if text is None:
                continue
            lower = text.lower()
            for marker, reason in forbidden.items():
                if marker.lower() in lower:
                    violations.append(
                        {
                            "path": str(path),
                            "marker": marker,
                            "reason": reason,
                        }
                    )
        return violations

    def _candidate_policy_scan_text(
        self,
        path: Path,
        *,
        source_project: Path | None,
        original_source_project: Path | None,
    ) -> str | None:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        if source_project is None or original_source_project is None:
            return text
        try:
            rel = path.resolve(strict=False).relative_to(source_project.resolve(strict=False))
        except ValueError:
            return text
        original_path = original_source_project / rel
        try:
            original_text = original_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return text
        if text == original_text:
            return ""
        return _added_policy_lines(original_text, text)

    def _proposer_access_violations(
        self,
        result: Any,
        *,
        workspace_dir: Path,
    ) -> list[dict[str, str]]:
        tool_access = getattr(result, "tool_access", None)
        if not isinstance(tool_access, dict):
            return []
        if self._proposer_allows_container_internal_access():
            return []

        allowed_roots = [workspace_dir]
        violations: list[dict[str, str]] = []

        for raw_path in sorted((tool_access.get("files_read") or {}).keys()):
            path = self._normalize_agent_access_path(raw_path, base_dir=workspace_dir)
            if not self._path_is_under_any(path, allowed_roots):
                violations.append(
                    {
                        "operation": "read",
                        "path": str(path),
                        "reason": "proposer reads must stay inside the scoped workspace",
                    }
                )

        for raw_path in sorted((tool_access.get("files_written") or {}).keys()):
            path = self._normalize_agent_access_path(raw_path, base_dir=workspace_dir)
            if not self._path_is_under_any(path, allowed_roots):
                violations.append(
                    {
                        "operation": "write",
                        "path": str(path),
                        "reason": "proposer writes must stay inside the scoped workspace",
                    }
                )
        return violations

    def _proposer_allows_container_internal_access(self) -> bool:
        return self.config.proposer_sandbox.strip().lower() == "docker"

    def _access_retry_note(
        self,
        *,
        violations: list[dict[str, str]],
        workspace_dir: Path,
    ) -> str:
        lines = [
            "## Retry Required: Filesystem Boundary Violation",
            "",
            "Your previous attempt read or wrote files outside the proposer workspace.",
            f"Allowed workspace root: `{workspace_dir.resolve(strict=False)}`",
            "",
            "Do not use absolute paths or `..` paths that leave this directory.",
            "Use only the files copied into the current working directory for this proposer call.",
            "Recreate exactly one candidate from scratch and write a fresh `pending_eval.json`.",
            "",
            "Violations from the previous attempt:",
        ]
        for item in violations:
            operation = item.get("operation", "access")
            path = item.get("path", "")
            reason = item.get("reason", "")
            lines.append(f"- {operation}: `{path}` ({reason})")
        return "\n".join(lines)

    def _normalize_agent_access_path(
        self,
        raw_path: str,
        *,
        base_dir: Path | None = None,
    ) -> Path:
        path = Path(str(raw_path)).expanduser()
        if path.is_absolute() and base_dir is not None:
            path = self._map_container_workspace_path(path, workspace_dir=base_dir)
        if not path.is_absolute():
            path = (base_dir or self.project_root) / path
        return path.resolve(strict=False)

    def _path_is_under_any(self, path: Path, roots: list[Path]) -> bool:
        normalized = path.resolve(strict=False)
        for root in roots:
            root_path = root.resolve(strict=False)
            if normalized == root_path or root_path in normalized.parents:
                return True
        return False

    def _path_matches_any(self, path: Path, files: list[Path]) -> bool:
        normalized = path.resolve(strict=False)
        return any(normalized == item.resolve(strict=False) for item in files)

    def _candidate_policy_scan_paths(self, candidate: dict[str, Any]) -> list[Path]:
        out: list[Path] = []
        module_path = str(candidate.get("module_path") or "").strip()
        if module_path:
            path = Path(module_path).expanduser()
            if not path.is_absolute():
                path = self.project_root / path
            out.append(path)

        candidate_root = candidate.get("candidate_root") or candidate.get("generated_dir")
        root: Path | None = None
        if candidate_root:
            root = Path(str(candidate_root)).expanduser()
            if not root.is_absolute():
                root = self.project_root / root
        module_name = str(candidate.get("module") or "").strip()
        if root is not None and root.exists():
            if module_name:
                rel = Path(*module_name.split(".")).with_suffix(".py")
                module_file = root / rel
                if module_file.exists():
                    out.append(module_file)
            # Historical candidates may import earlier run-local parent modules.
            # Scan that workspace so contaminated parent modules remain visible
            # to the policy check.
            out.extend(sorted(root.glob("*.py")))

        source_project = self._candidate_source_project_root(candidate)
        if source_project is not None:
            package_dir = source_project / "src" / "worldcalib"
            if package_dir.exists():
                out.extend(sorted(package_dir.rglob("*.py")))
        return sorted(set(out))

    def _candidate_source_project_root(self, candidate: dict[str, Any]) -> Path | None:
        extra = candidate.get("extra") if isinstance(candidate.get("extra"), dict) else {}
        for key in ("source_project_path", "project_source_path", "memomemo_source_path"):
            value = candidate.get(key) or extra.get(key)
            if not value:
                continue
            path = Path(str(value)).expanduser()
            if not path.is_absolute():
                path = self.project_root / path
            if (path / "src").exists():
                return path
            if path.name == "src":
                return path.parent
            return path
        return None

    def _candidate_original_source_project_root(self, source_project: Path) -> Path | None:
        candidate_dir = source_project.parent if source_project.name == "project_source" else None
        if candidate_dir is not None:
            original = candidate_dir / "original_project_source"
            if (original / "src").exists():
                return original

        for parent in source_project.parents:
            manifest_path = parent / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            original_value = manifest.get("original_project_source")
            if not original_value:
                continue
            original = Path(str(original_value)).expanduser()
            if not original.is_absolute():
                original = manifest_path.parent / original
            if (original / "src").exists():
                return original
        return None

    def _load_existing_candidates(self) -> list[CandidateResult]:
        out: list[CandidateResult] = []
        for path in sorted((self.run_dir / "candidate_results").glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                out.append(CandidateResult.from_dict(payload["candidate"]))
            except Exception:
                continue
        return out

    def _resume_start_iteration(self, candidates: list[CandidateResult]) -> int:
        """First iteration to (re)run on ``--resume``.

        Iterations that already produced a stored candidate are treated as
        complete (this includes iterations whose proposer ran but whose
        candidate was rejected by the selection policy — those budget rounds
        were spent). We resume at ``max(completed) + 1``; if nothing past
        the seed is stored we start at 1, and if every iteration through
        ``config.iterations`` is already done the train loop is a no-op and
        only the test-frontier step (if enabled) runs.
        """

        completed = {it for it in self._candidate_iterations(candidates) if it >= 1}
        return (max(completed) + 1) if completed else 1

    def _clean_stale_iteration_artifacts(self, start_iteration: int) -> None:
        """Remove per-iteration dirs and dangling jsonl rows for iterations
        ``>= start_iteration`` before a ``--resume`` rerun.

        Crashed/partial ``proposer_calls/iter_NNN`` dirs and the
        ``proposer_failed`` rows they left in ``evolution_summary.jsonl`` /
        ``diff_summary.jsonl`` would otherwise shadow the fresh run."""

        calls_dir = self.run_dir / "proposer_calls"
        if calls_dir.exists():
            for child in calls_dir.iterdir():
                iteration = _iteration_from_dir_name(child.name)
                if iteration is not None and iteration >= start_iteration and child.is_dir():
                    shutil.rmtree(child)

        for path in (self.summary_path, self.diff_summary_path):
            if not path.exists():
                continue
            kept: list[str] = []
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    iteration = row.get("iteration")
                except (json.JSONDecodeError, AttributeError):
                    kept.append(line)
                    continue
                if isinstance(iteration, int) and iteration >= start_iteration:
                    continue
                kept.append(line)
            path.write_text(
                ("\n".join(kept) + "\n") if kept else "", encoding="utf-8"
            )

    def _iteration_dir(self, iteration: int) -> Path:
        return self.run_dir / "proposer_calls" / f"iter_{iteration:03d}"

    def _workspace_dir(self, iteration: int) -> Path:
        return self._iteration_dir(iteration) / "workspace"

    def _seed_passrate(self, candidates: list[CandidateResult]) -> float:
        """Return the seed (iter-0) candidate's passrate, or 0.0 if none.

        Seed candidates are those without an ``iterNNN_`` prefix in
        ``candidate_id``.  When the user supplies ``--baseline-dir`` the
        baseline candidates are also counted as seeds.  The maximum is
        used so repeated MemGPT seed variants collapse to
        a single baseline floor.
        """

        seeds = [
            item
            for item in candidates
            if _candidate_iteration(item.candidate_id) is None
        ]
        return max((item.passrate for item in seeds), default=0.0)

    def _iteration_parent_map(self, *, iteration: int) -> dict[int, int]:
        """Reconstruct the patch-base parent edge for every prior iteration.

        Reads each ``proposer_calls/iter_NNN/assignment.json`` (the
        authoritative record of the harness-forced base) and maps
        ``child_iter -> parent_iter``. A null/absent ``base_iter`` means the
        iteration was grown from the clean seed, so its parent is the
        immortal root ``0``. Reading from disk keeps the tree correct across
        ``--resume`` without depending on in-memory state.
        """

        parents: dict[int, int] = {}
        for i in range(1, iteration):
            base: int | None = None
            # Prefer the proposer-DECLARED parent (candidate config
            # ``base_iter`` in the archived pending_eval.json): under the
            # ``self`` policy the proposer may replace or graft over the
            # harness-materialised default, so its declaration is the honest
            # lineage edge.
            pending = self._iteration_dir(i) / "pending_eval.json"
            if pending.exists():
                try:
                    payload = json.loads(pending.read_text(encoding="utf-8"))
                    declared = (payload.get("candidates") or [{}])[0].get("base_iter")
                    if declared is not None:
                        base = int(declared)
                except (json.JSONDecodeError, OSError, TypeError, ValueError):
                    base = None
            if base is None:
                assignment = self._iteration_dir(i) / "assignment.json"
                if not assignment.exists():
                    continue
                try:
                    data = json.loads(assignment.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                raw = data.get("base_iter")
                base = 0 if raw is None else int(raw)
            parents[i] = base
        return parents

    def _self_select_default_base(
        self,
        existing_candidates: list[CandidateResult],
        *,
        iteration: int,
    ) -> int | None:
        """Default patch base for the ``self`` selection policy.

        Lex-best among prior candidates: passrate desc, average_score desc,
        later iteration wins remaining ties — restricted to candidates whose
        archived source snapshot is on disk and whose passrate strictly
        exceeds the seed baseline. Returns ``None`` (clean seed) when nothing
        beats the seed yet. This is only the DEFAULT materialised into
        ``project_source/``; the proposer is free to override it (see
        ``frontier_manifest.json`` + the Starting Point prompt block).
        """

        baseline = self._seed_passrate(existing_candidates)
        best_key: tuple[float, float, int] | None = None
        for item in existing_candidates:
            base_iter = _candidate_iteration(item.candidate_id)
            if base_iter is None or base_iter <= 0 or base_iter >= iteration:
                continue
            if item.passrate <= baseline:
                continue
            base_source = (
                self._iteration_dir(base_iter)
                / "source_snapshot"
                / "candidate"
                / "project_source"
            )
            if not base_source.exists():
                continue
            key = (
                float(item.passrate),
                float(item.average_score or 0.0),
                base_iter,
            )
            if best_key is None or key > best_key:
                best_key = key
        return None if best_key is None else best_key[2]

    def _write_self_select_manifest(
        self,
        workspace_dir: Path,
        existing_candidates: list[CandidateResult],
        *,
        iteration: int,
        default_base_iter: int | None,
        reference_iterations: tuple[int, ...],
    ) -> None:
        """Write ``frontier_manifest.json`` + ``task_score_matrix.json``.

        The manifest gives the proposer every prior candidate's headline
        metrics, hypothesis, lineage edge, and (when staged) the
        workspace-relative path to its full source snapshot. The matrix is
        the full iteration x task score history — deliberately NOT a
        per-task max, so the proposer can judge variance from the raw
        history instead of chasing one-off highs. Both files are staged for
        the calib AND nowmc arms: the arm delta must stay confined to the
        calibration protocol, not the evidence surface. Best-effort.
        """

        from worldcalib.prediction_feedback import load_score_breakdown

        try:
            parents = self._iteration_parent_map(iteration=iteration)
            staged = set(reference_iterations)
            rows: list[dict[str, Any]] = []
            matrix: dict[str, dict[str, float]] = {}
            ordered = sorted(
                existing_candidates,
                key=lambda c: (
                    _candidate_iteration(c.candidate_id) or 0,
                    c.candidate_id,
                ),
            )
            for item in ordered:
                cand_iter = _candidate_iteration(item.candidate_id) or 0
                if cand_iter >= iteration and cand_iter != 0:
                    continue
                config = item.config if isinstance(item.config, dict) else {}
                hypothesis = str(config.get("hypothesis") or "").strip()
                snapshot_rel = (
                    f"reference_iterations/iter_{cand_iter:03d}/source_snapshot"
                    if cand_iter in staged
                    else None
                )
                rows.append(
                    {
                        "iteration": cand_iter,
                        "candidate_id": item.candidate_id,
                        "passrate": item.passrate,
                        "average_score": item.average_score,
                        "parent_iter": parents.get(cand_iter),
                        "hypothesis": hypothesis.split("\n")[0][:240],
                        "source_snapshot": snapshot_rel,
                        "is_default_base": cand_iter == default_base_iter,
                    }
                )
                result_path = self._calib_result_path(item)
                if result_path is None:
                    continue
                breakdown = load_score_breakdown(result_path)
                col = f"iter_{cand_iter:03d}"
                for task_id, cell in breakdown.items():
                    if task_id == "all" or not isinstance(cell, dict):
                        continue
                    score = cell.get("average_score")
                    if score is None:
                        continue
                    matrix.setdefault(str(task_id), {})[col] = float(score)

            manifest = {
                "iteration": iteration,
                "default_base_iter": default_base_iter,
                "note": (
                    "YOU choose the parent. Each staged candidate's full source "
                    "is at <source_snapshot>; the default base is already in "
                    "project_source/. Judge per-task variance from "
                    "task_score_matrix.json history, not single highs."
                ),
                "candidates": rows,
            }
            (workspace_dir / "frontier_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            (workspace_dir / "task_score_matrix.json").write_text(
                json.dumps(
                    {
                        "metric": "average_score per task/type, one column per iteration",
                        "tasks": matrix,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 - advisory artifacts only
            self._append_event(
                {
                    "event": "self_select_manifest_failed",
                    "iteration": iteration,
                    "error": repr(exc),
                }
            )

    def _state_snapshot_base_iteration(
        self,
        existing_candidates: list[CandidateResult],
        *,
        iteration: int,
    ) -> int | None:
        """Choose the comparison base rendered in organized ``state.md``.

        Default-policy proposer iterations still edit a clean source snapshot;
        this base is only the state/evidence anchor. Prefer the current quality
        frontier's strongest evaluated iteration, and fall back to the seed
        baseline (iteration 0) when no positive iteration exists yet.
        """

        if not existing_candidates:
            return None
        candidates = self._quality_frontier(existing_candidates) or existing_candidates
        sorted_candidates = sorted(candidates, key=_candidate_score, reverse=True)
        has_seed = False
        for candidate in sorted_candidates:
            candidate_iter = _candidate_iteration(candidate.candidate_id)
            if candidate_iter is None:
                has_seed = True
                continue
            if 0 <= candidate_iter < iteration:
                return candidate_iter
        if has_seed:
            return 0
        return None

    def _reference_iterations_for_budget(
        self,
        budget: str,
        *,
        iteration: int,
        candidates: list[CandidateResult],
    ) -> tuple[int, ...]:
        available = {
            item
            for item in self._candidate_iterations(candidates)
            if 0 < item < iteration and self._iteration_dir(item).exists()
        }
        if budget == "high":
            return tuple(sorted(available))

        if budget == "medium":
            best_k = self.config.progressive_medium_best_count
        else:
            best_k = self.config.progressive_low_best_count
        selected = self._best_iterations(candidates, k=best_k)
        out: list[int] = []
        seen: set[int] = set()
        for item in selected:
            if item not in available or item in seen:
                continue
            seen.add(item)
            out.append(item)
        return tuple(out)

    def _best_iterations(self, candidates: list[CandidateResult], *, k: int) -> list[int]:
        out: list[int] = []
        seen: set[int] = set()
        for candidate in sorted(candidates, key=_candidate_best_rank):
            iteration = _candidate_iteration(candidate.candidate_id)
            if iteration is None or iteration <= 0 or iteration in seen:
                continue
            seen.add(iteration)
            out.append(iteration)
            if len(out) >= k:
                break
        return out

    def _candidate_iterations(self, candidates: list[CandidateResult]) -> set[int]:
        out: set[int] = set()
        for candidate in candidates:
            iteration = _candidate_iteration(candidate.candidate_id)
            if iteration is not None:
                out.add(iteration)
        return out

    def _best_passrate(self, candidates: list[CandidateResult]) -> float:
        return max((item.passrate for item in candidates), default=0.0)

    def _refresh_run_indexes(self, candidates: list[CandidateResult]) -> None:
        self._write_candidate_score_table_from_candidates(candidates)
        if not self.retrieval_diagnostics_summary_path.exists():
            self.retrieval_diagnostics_summary_path.write_text("[]\n", encoding="utf-8")
        self._write_iteration_index(candidates)
        if not self.diff_summary_path.exists():
            self.diff_summary_path.write_text("", encoding="utf-8")

    def _write_candidate_score_table_from_candidates(
        self,
        candidates: list[CandidateResult],
    ) -> None:
        rows = []
        frontier_ids = self._quality_frontier_ids(candidates)
        best_passrate_ids = self._best_passrate_ids(candidates)
        for candidate in sorted(
            candidates,
            key=lambda item: ((_candidate_iteration(item.candidate_id) or 0), item.candidate_id),
        ):
            extra = self._candidate_extra(candidate)
            iteration = _candidate_iteration(candidate.candidate_id) or 0
            rows.append(
                {
                    "iteration": iteration,
                    "candidate_id": candidate.candidate_id,
                    "scaffold_name": candidate.scaffold_name,
                    "passrate": candidate.passrate,
                    "average_score": candidate.average_score,
                    "token_consuming": candidate.token_consuming,
                    "source_family": extra.get("source_family"),
                    "build_tag": extra.get("build_tag"),
                    "result_path": candidate.result_path,
                    "iteration_dir": str(self._iteration_dir(iteration)),
                    "is_best_passrate": candidate.candidate_id in best_passrate_ids,
                    "is_quality_frontier": candidate.candidate_id in frontier_ids,
                    # Audit-only flag from swebench eval-gate integrity check.
                    # Always present so dashboards can filter on it; non-SWE
                    # runs leave it False because their evaluators don't set
                    # this key on candidate.config.
                    "reward_hack_attempt": bool(
                        (candidate.config or {}).get("reward_hack_attempt", False)
                    ),
                }
            )
        self.candidate_score_table_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_iteration_index(self, candidates: list[CandidateResult]) -> None:
        by_iteration: dict[int, dict[str, Any]] = {}
        for candidate in candidates:
            iteration = _candidate_iteration(candidate.candidate_id) or 0
            call_dir = self._iteration_dir(iteration)
            row = by_iteration.setdefault(
                iteration,
                {
                    "iteration": iteration,
                    "iteration_dir": str(call_dir),
                    "candidate_ids": [],
                    "candidate_result_paths": [],
                    "compact_result_path": str(call_dir / "eval" / "candidate_result.compact.json"),
                    "retrieval_diagnostics_path": str(
                        call_dir / "eval" / "retrieval_diagnostics.json"
                    ),
                    "diff_path": str(call_dir / "diff.patch"),
                    "diff_digest_path": str(call_dir / "diff_digest.md"),
                    "source_snapshot_dir": str(call_dir / "source_snapshot"),
                    "generated_dir": str(call_dir / "generated"),
                },
            )
            row["candidate_ids"].append(candidate.candidate_id)
            row["candidate_result_paths"].append(candidate.result_path)

        for call_dir in sorted((self.run_dir / "proposer_calls").glob("iter_*")):
            iteration = _iteration_from_dir_name(call_dir.name)
            if iteration is None:
                continue
            by_iteration.setdefault(
                iteration,
                {
                    "iteration": iteration,
                    "iteration_dir": str(call_dir),
                    "candidate_ids": [],
                    "candidate_result_paths": [],
                    "compact_result_path": str(call_dir / "eval" / "candidate_result.compact.json"),
                    "retrieval_diagnostics_path": str(
                        call_dir / "eval" / "retrieval_diagnostics.json"
                    ),
                    "diff_path": str(call_dir / "diff.patch"),
                    "diff_digest_path": str(call_dir / "diff_digest.md"),
                    "source_snapshot_dir": str(call_dir / "source_snapshot"),
                    "generated_dir": str(call_dir / "generated"),
                },
            )

        rows = [by_iteration[key] for key in sorted(by_iteration)]
        self.iteration_index_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _optimization_direction_lines(self, target_system: str | None = None) -> tuple[str, ...]:
        """Return prompt-only optimization directions for proposers."""

        lines: list[str] = []
        target = target_system or self.config.progressive_target_system
        for cell in get_target_cells(target):
            focus = ", ".join(cell.focus_functions) if cell.focus_functions else "all functions"
            lines.append(
                f"{cell.name}: {cell.description} Focus areas: {focus}. "
                f"Guidance: {cell.prompt_guidance}"
            )
        if not lines:
            lines.append(
                "global: improve memory construction, retrieval, evidence selection, "
                "and answering."
            )
        return tuple(lines)

    def _candidate_extra(self, candidate: CandidateResult) -> dict[str, Any]:
        extra = candidate.config.get("extra") if isinstance(candidate.config, dict) else None
        if isinstance(extra, dict):
            return dict(extra)
        return {}

    def _infer_source_family(self, candidate: CandidateResult) -> str:
        extra = candidate.config.get("extra") if isinstance(candidate.config, dict) else None
        if isinstance(extra, dict):
            source_family = str(extra.get("source_family") or "").lower()
            if source_family == "memgpt":
                return source_family
        text = f"{candidate.candidate_id} {candidate.scaffold_name}".lower()
        if "memgpt" in text or "letta" in text:
            return "memgpt"
        return "memgpt"

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
        generated_dir = generated_dir or self.generated_dir
        snapshot_root = snapshot_root or (
            generated_dir / "source_snapshots" / f"iter_{iteration:03d}"
        )
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root)
        snapshot_root.mkdir(parents=True, exist_ok=True)
        self._ensure_package_dirs(snapshot_root, root=snapshot_root)

        scaffold_source = self._source_scaffold_path(source_family)
        source_files = [path for path in (scaffold_source,) if path is not None and path.exists()]

        candidate_dir = snapshot_root / "candidate"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_package_dirs(candidate_dir, root=snapshot_root)
        for path in source_files:
            self._copy_if_exists(path, candidate_dir / path.name)
        self._copy_project_source_context(candidate_dir)
        # Always seed `original_project_source/` directly from the baseline
        # so the on-disk diff captures cumulative evolution from baseline
        # regardless of what `project_source/` is replaced with below.
        original_project_source = candidate_dir / "original_project_source"
        if original_project_source.exists():
            shutil.rmtree(original_project_source)
        self._copy_baseline_project_source_into(original_project_source)
        project_source = candidate_dir / "project_source"
        # If a curaii-style parent base was supplied, replace the freshly
        # baseline-seeded `project_source/` with that parent's archived
        # source so the proposer edits on top of a previously evaluated
        # candidate rather than restarting from baseline.
        if base_iter is not None:
            parent_source = (
                self._iteration_dir(base_iter)
                / "source_snapshot"
                / "candidate"
                / "project_source"
            )
            if parent_source.exists():
                if project_source.exists():
                    shutil.rmtree(project_source)
                shutil.copytree(
                    parent_source,
                    project_source,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        self._copy_upstream_source_context(source_family, candidate_dir)
        upstream_source = candidate_dir / "upstream_source"
        original_upstream_source = candidate_dir / "original_upstream_source"
        if original_upstream_source.exists():
            shutil.rmtree(original_upstream_source)
        if upstream_source.exists():
            shutil.copytree(
                upstream_source,
                original_upstream_source,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "build"),
            )
        self._copy_if_exists(
            self.project_root / "src" / "worldcalib" / "scaffolds" / "base.py",
            candidate_dir / "base.py",
        )
        self._copy_if_exists(
            self.project_root / "src" / "worldcalib" / "schemas.py",
            candidate_dir / "schemas.py",
        )
        if base_iter is not None:
            base_anchor_lines = [
                f"Patch base: iter_{base_iter:03d} (curaii lineage anchor).",
                "`project_source/` is initialized from that iteration's archived",
                "candidate source. `original_project_source/` remains the clean",
                "baseline so `diff.patch` records cumulative evolution from baseline.",
            ]
        else:
            base_anchor_lines = [
                "Historical iterations are diagnostic references only; do not treat",
                "their source snapshots as editable parents.",
            ]
        (candidate_dir / "SNAPSHOT.md").write_text(
            "\n".join(
                [
                    "# Source Snapshot Candidate",
                    "",
                    f"Iteration: {iteration}",
                    f"Source family: {source_family}",
                    f"Target system: {target_system or source_family}",
                    "",
                    "This directory is a writable candidate-specific clean source snapshot.",
                    "It also contains benchmark-scoped project source under",
                    "`project_source/src/worldcalib` and relevant upstream source",
                    "under `upstream_source` for inspection.",
                    *base_anchor_lines,
                    "Existing source-backed base memories are read-only. You may edit",
                    "copied build/database-construction paths such as add/build/schema/",
                    "extraction/evolution/embedding or persistence layout, but source",
                    "edits that alter persisted memories must use a fresh source_base_dir",
                    "and build_tag in pending_eval.json.",
                    "Modify files here for the mechanism under test, then expose the",
                    "edited built-in source scaffold in `pending_eval.json` with",
                    "`scaffold_name` and `extra.source_project_path`.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        manifest = {
            "iteration": iteration,
            "source_family": source_family,
            "target_system": target_system or source_family,
            "benchmark": self.workspace_spec.benchmark,
            "candidate_dir": str(candidate_dir),
            "project_source": str(project_source),
            "original_project_source": str(original_project_source),
            "primary_source_file": self.workspace_spec.primary_source_file,
            "project_source_files": list(self.workspace_spec.source_files),
            "source_files": [str(path) for path in source_files],
            "base_iter": base_iter,
        }
        (snapshot_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (call_dir / "source_snapshot_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return snapshot_root

    def _ensure_package_dirs(self, path: Path, *, root: Path | None = None) -> None:
        generated_root = root or self.generated_dir
        current = generated_root
        while True:
            current.mkdir(parents=True, exist_ok=True)
            init = current / "__init__.py"
            if not init.exists():
                init.write_text('"""Generated source snapshot package."""\n', encoding="utf-8")
            if current == path:
                break
            try:
                rel = path.relative_to(current)
            except ValueError:
                break
            parts = rel.parts
            if not parts:
                break
            current = current / parts[0]

    def _copy_iteration_bundle(self, src: Path, dest: Path) -> None:
        if not src.exists():
            return
        if dest.exists():
            shutil.rmtree(dest)
        ignore = shutil.ignore_patterns(
            "workspace",
            "context",
            "claude_session",
            "__pycache__",
            "*.pyc",
        )
        shutil.copytree(src, dest, ignore=ignore)

    def _copy_if_exists(self, src: Path, dest: Path) -> None:
        if src.exists() and src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def _sync_workspace_outputs(
        self,
        *,
        workspace_dir: Path,
        call_dir: Path,
    ) -> None:
        workspace_generated_dir = workspace_dir / "generated"
        if workspace_generated_dir.exists():
            self.generated_dir.mkdir(parents=True, exist_ok=True)
            self._ensure_package_dirs(self.generated_dir)
            call_generated_dir = call_dir / "generated"
            if call_generated_dir.exists():
                shutil.rmtree(call_generated_dir)
            call_generated_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(workspace_generated_dir.rglob("*")):
                if not src.is_file():
                    continue
                if "__pycache__" in src.parts or src.suffix == ".pyc":
                    continue
                rel = src.relative_to(workspace_generated_dir)
                dest = self.generated_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                call_dest = call_generated_dir / rel
                call_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, call_dest)

        workspace_pending = workspace_dir / "pending_eval.json"
        if workspace_pending.exists():
            self._copy_if_exists(workspace_pending, self.pending_eval_path)
            self._copy_if_exists(workspace_pending, call_dir / "pending_eval.raw.json")

    def _pending_eval_is_salvageable(self) -> bool:
        """Whether a written ``pending_eval.json`` can be salvaged.

        A timed-out or non-zero-exit proposer may still have written a
        complete candidate before it was killed. Returns ``True`` only when
        the archived ``pending_eval.json`` parses cleanly and holds exactly
        one candidate, so a salvage cannot smuggle in a truncated or empty
        file. A partial write fails the parse and is treated as a real
        failure rather than retried (a retry would just time out again).
        """
        if not self.pending_eval_path.exists():
            return False
        try:
            pending = json.loads(self.pending_eval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return len(_pending_candidates(pending)) == 1

    def _normalize_workspace_candidate_paths(
        self,
        candidate: dict[str, Any],
        *,
        workspace_dir: Path,
        workspace_generated_dir: Path,
    ) -> None:
        candidate["candidate_root"] = str(self.generated_dir)
        if candidate.get("generated_dir"):
            candidate["generated_dir"] = str(self.generated_dir)
        self._normalize_workspace_path_fields(candidate, workspace_dir, workspace_generated_dir)
        extra = candidate.get("extra")
        if isinstance(extra, dict):
            self._normalize_workspace_path_fields(extra, workspace_dir, workspace_generated_dir)

    def _normalize_workspace_path_fields(
        self,
        payload: dict[str, Any],
        workspace_dir: Path,
        workspace_generated_dir: Path,
    ) -> None:
        for key in (
            "module_path",
            "source_path",
            "source_project_path",
            "project_source_path",
            "memomemo_source_path",
            "upstream_source_path",
            "memgpt_source_path",
            "mini_swe_agent_source_path",
            "source_base_dir",
            "base_memory_dir",
        ):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            payload[key] = str(
                self._resolve_workspace_path(
                    value,
                    workspace_dir=workspace_dir,
                    workspace_generated_dir=workspace_generated_dir,
                )
            )

    def _rewrite_workspace_source_paths_to_archive(
        self,
        candidate: dict[str, Any],
        *,
        workspace_dir: Path,
        archived_source_snapshot: Path,
    ) -> None:
        self._rewrite_workspace_source_path_fields(
            candidate,
            workspace_dir=workspace_dir,
            archived_source_snapshot=archived_source_snapshot,
        )
        extra = candidate.get("extra")
        if isinstance(extra, dict):
            self._rewrite_workspace_source_path_fields(
                extra,
                workspace_dir=workspace_dir,
                archived_source_snapshot=archived_source_snapshot,
            )

    def _rewrite_workspace_source_path_fields(
        self,
        payload: dict[str, Any],
        *,
        workspace_dir: Path,
        archived_source_snapshot: Path,
    ) -> None:
        workspace_source = (workspace_dir / "source_snapshot").resolve(strict=False)
        archived_source = archived_source_snapshot.resolve(strict=False)
        for key in (
            "source_snapshot_path",
            "source_project_path",
            "project_source_path",
            "memomemo_source_path",
            "upstream_source_path",
            "memgpt_source_path",
            "mini_swe_agent_source_path",
        ):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = workspace_dir / path
            path = self._map_container_workspace_path(path, workspace_dir=workspace_dir)
            resolved = path.resolve(strict=False)
            if resolved == workspace_source or workspace_source in resolved.parents:
                rel = resolved.relative_to(workspace_source)
                payload[key] = str((archived_source / rel).resolve(strict=False))

    def _resolve_workspace_path(
        self,
        value: str,
        *,
        workspace_dir: Path,
        workspace_generated_dir: Path,
    ) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            path = self._map_container_workspace_path(path, workspace_dir=workspace_dir)
        if not path.is_absolute():
            path = workspace_dir / path
        resolved = path.resolve(strict=False)
        workspace_generated = workspace_generated_dir.resolve(strict=False)
        if resolved == workspace_generated or workspace_generated in resolved.parents:
            rel = resolved.relative_to(workspace_generated)
            return (self.generated_dir / rel).resolve(strict=False)
        return resolved

    def _map_container_workspace_path(self, path: Path, *, workspace_dir: Path) -> Path:
        if self.config.proposer_sandbox.strip().lower() != "docker":
            return path
        container_root = Path(self.config.proposer_docker_workspace or "/workspace")
        try:
            rel = path.relative_to(container_root)
        except ValueError:
            return path
        return workspace_dir / rel

    def _copy_tree_if_exists(
        self,
        src: Path,
        dest: Path,
        *,
        ignore_names: tuple[str, ...] = (),
    ) -> None:
        if not src.exists() or not src.is_dir():
            return
        if dest.exists():
            shutil.rmtree(dest)
        ignore_patterns = (
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "*.pyc",
            *ignore_names,
        )
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns(*ignore_patterns),
        )

    def _copy_baseline_project_source_into(self, target_root: Path) -> list[str]:
        """Copy the baseline project source into ``target_root/src/worldcalib``.

        Returns the list of files copied (used by the caller to write a
        manifest, when applicable).
        """

        return list(
            copy_benchmark_project_source(
                project_root=self.project_root,
                dest_pkg=target_root / "src" / "worldcalib",
                spec=self.workspace_spec,
            )
        )

    def _copy_project_source_context(self, dest_dir: Path) -> None:
        copied = self._copy_baseline_project_source_into(dest_dir / "project_source")
        (dest_dir / "project_source_manifest.json").write_text(
            json.dumps(
                {
                    "benchmark": self.workspace_spec.benchmark,
                    "primary_source_file": self.workspace_spec.primary_source_file,
                    "source_files": list(copied),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _source_scaffold_path(self, source_family: str) -> Path | None:
        mapping = {
            "memgpt": "memgpt_scaffold.py",
        }
        name = mapping.get(source_family)
        if not name:
            return None
        return self.project_root / "src" / "worldcalib" / "scaffolds" / name

    def _copy_upstream_source_context(self, source_family: str, dest_dir: Path) -> None:
        upstream_dir = dest_dir / "upstream_source"
        if source_family == "memgpt":
            self._copy_tree_if_exists(
                self.project_root / "references" / "vendor" / "MemGPT",
                upstream_dir / "MemGPT",
            )

    def _best_passrate_ids(self, candidates: list[CandidateResult]) -> set[str]:
        if not candidates:
            return set()
        best = max(item.passrate for item in candidates)
        return {item.candidate_id for item in candidates if item.passrate == best}

    def _quality_frontier(self, candidates: list[CandidateResult]) -> list[CandidateResult]:
        if not candidates:
            return []
        by_id = {item.candidate_id: item for item in candidates}
        points = [
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
            for item in candidates
        ]
        return [by_id[point.candidate_id] for point in pareto_frontier(points)]

    def _quality_frontier_ids(self, candidates: list[CandidateResult]) -> set[str]:
        return {item.candidate_id for item in self._quality_frontier(candidates)}

    def _best_quality_value(self, candidates: list[CandidateResult]) -> float:
        return max((_candidate_quality_value(item) for item in candidates), default=0.0)

    def _save_best_candidates(self, candidates: list[CandidateResult]) -> None:
        self.frontier_path.parent.mkdir(parents=True, exist_ok=True)
        frontier = self._quality_frontier(candidates)
        payload = [item.to_dict() for item in frontier]
        self.frontier_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.run_store.update_frontier(
            as_of_iteration=max(
                (_candidate_iteration(item.candidate_id) or 0 for item in candidates),
                default=0,
            ),
            candidates=candidates,
            frontier=frontier,
        )
        self._sync_pareto_frontier_index(candidates, frontier)

    def _sync_pareto_frontier_index(
        self,
        candidates: list[CandidateResult],
        frontier: list[CandidateResult],
    ) -> None:
        """Mirror the current pareto frontier into iteration_meta.

        Builds a {iteration → on_pareto_frontier} map across every iter
        we have at least one candidate for, then bulk-updates the
        ``iteration_meta`` table so MCP queries see a consistent
        snapshot. No-op when the trace index does not yet exist.
        """

        if not candidates:
            return
        if not self.trace_harness.indexer.db_path.exists():
            return
        frontier_iters = {
            _candidate_iteration(item.candidate_id)
            for item in frontier
        }
        frontier_iters.discard(None)
        flags: dict[int, bool] = {}
        for candidate in candidates:
            iteration = _candidate_iteration(candidate.candidate_id)
            if iteration is None:
                continue
            flags[iteration] = iteration in frontier_iters
        if flags:
            self.trace_harness.indexer.refresh_pareto_frontier(flags)

    def _append_summary(
        self,
        *,
        iteration: int,
        candidate: CandidateResult,
        proposal: dict[str, Any] | None = None,
    ) -> None:
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "iteration": iteration,
            "candidate": candidate.to_dict(),
            "proposal": proposal or {},
            "self_best": [candidate.to_dict()],
        }
        self.run_store.record_candidates(
            iteration,
            [candidate],
            proposals_by_candidate={candidate.candidate_id: proposal or {}},
        )
        self._refresh_run_store(iteration)
        self._append_event(row)

    def _append_proposer_result_event(
        self,
        *,
        iteration: int,
        result: Any,
        selection_policy: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        tool_access_raw = getattr(result, "tool_access", {}) or {}
        tool_access = tool_access_raw if isinstance(tool_access_raw, dict) else {}
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "iteration": iteration,
            "event": "proposer_result",
            "selection_policy": selection_policy,
            "proposer_agent": self.config.proposer_agent,
            "returncode": getattr(result, "returncode", None),
            "timed_out": bool(getattr(result, "timed_out", False)),
            "proposer_metrics": getattr(result, "metrics", {}) or {},
            "usage": getattr(result, "usage", None),
            "files_read": tool_access.get("files_read", {}),
            "files_written": tool_access.get("files_written", {}),
            "grep_requests": tool_access.get("grep_requests", []),
            "tool_counts": tool_access.get("tool_counts", {}),
            "evidence_usage": tool_access.get("evidence_usage", {}),
        }
        if extra:
            row.update(extra)
        self.run_store.record_proposer_call(
            iteration,
            result=result,
            selection_policy=selection_policy,
            proposer_agent=self.config.proposer_agent,
            extra=extra or {},
        )
        self._refresh_run_store(iteration)
        self._append_event(row)

    def _aggregate_proposer_metrics(self) -> dict[str, Any]:
        if not self.summary_path.exists():
            return {}

        totals = {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "total_reported_tokens": 0,
            "estimated_cost_usd": 0.0,
            "duration_s": 0.0,
            "tool_calls": 0,
            "read_file_calls": 0,
            "read_lines": 0,
            "write_file_calls": 0,
            "written_lines": 0,
            "runstore_tool_calls": 0,
            "runstore_trace_tool_calls": 0,
            "runstore_mod_tool_calls": 0,
            "raw_trace_file_reads": 0,
            "raw_reference_file_reads": 0,
            "raw_summary_file_reads": 0,
            "raw_evidence_file_reads": 0,
            "evidence_usage_events": 0,
        }
        tool_counts: dict[str, int] = {}
        unique_files_read: set[str] = set()

        for line in self.summary_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "proposer_result":
                continue

            metrics = row.get("proposer_metrics") or {}
            if not isinstance(metrics, dict):
                metrics = {}
            totals["calls"] += 1
            for key in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "total_reported_tokens",
                "tool_calls",
                "read_file_calls",
                "read_lines",
                "write_file_calls",
                "written_lines",
            ):
                totals[key] += _int_metric(metrics.get(key))
            for key in ("estimated_cost_usd", "duration_s"):
                totals[key] += _float_metric(metrics.get(key))

            evidence_usage = row.get("evidence_usage") or metrics.get("evidence_usage") or {}
            if isinstance(evidence_usage, dict):
                for key in (
                    "runstore_tool_calls",
                    "runstore_trace_tool_calls",
                    "runstore_mod_tool_calls",
                    "raw_trace_file_reads",
                    "raw_reference_file_reads",
                    "raw_summary_file_reads",
                    "raw_evidence_file_reads",
                    "evidence_usage_events",
                ):
                    totals[key] += _int_metric(evidence_usage.get(key))

            row_tool_counts = row.get("tool_counts") or metrics.get("tool_counts") or {}
            if isinstance(row_tool_counts, dict):
                for name, count in row_tool_counts.items():
                    tool_counts[str(name)] = tool_counts.get(str(name), 0) + _int_metric(
                        count
                    )

            files_read = row.get("files_read") or {}
            if isinstance(files_read, dict):
                unique_files_read.update(str(path) for path in files_read)

        totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 6)
        totals["duration_s"] = round(totals["duration_s"], 3)
        totals["unique_files_read"] = len(unique_files_read)
        totals["tool_counts"] = dict(sorted(tool_counts.items()))
        events = totals["evidence_usage_events"]
        totals["evidence_usage_rate"] = (
            round(totals["runstore_tool_calls"] / events, 4) if events else 0.0
        )
        return totals

    def _append_event(self, row: dict[str, Any]) -> None:
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        with self.summary_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


LocomoOptimizerConfig = OptimizerConfig
MemoOptimizer = LocomoOptimizer


def _candidate_score(item: CandidateResult) -> tuple[float, int, str]:
    return (item.passrate, item.average_score, -item.token_consuming, item.candidate_id)


def _candidate_quality_value(item: CandidateResult) -> float:
    return item.passrate


def _candidate_best_rank(item: CandidateResult) -> tuple[float, float, int, str]:
    return (-item.passrate, -item.average_score, item.token_consuming, item.candidate_id)


def _candidate_iteration(candidate_id: str) -> int | None:
    if not candidate_id.startswith("iter"):
        return None
    digits = []
    for char in candidate_id[4:]:
        if not char.isdigit():
            break
        digits.append(char)
    if not digits:
        return None
    return int("".join(digits))


def _iteration_from_dir_name(name: str) -> int | None:
    if not name.startswith("iter_"):
        return None
    try:
        return int(name.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def _added_policy_lines(original: str, updated: str) -> str:
    original_lines = original.splitlines()
    updated_lines = updated.splitlines()
    prefix = 0
    limit = min(len(original_lines), len(updated_lines))
    while prefix < limit and original_lines[prefix] == updated_lines[prefix]:
        prefix += 1

    suffix = 0
    original_remaining = len(original_lines) - prefix
    updated_remaining = len(updated_lines) - prefix
    while (
        suffix < original_remaining
        and suffix < updated_remaining
        and original_lines[len(original_lines) - 1 - suffix]
        == updated_lines[len(updated_lines) - 1 - suffix]
    ):
        suffix += 1

    end = len(updated_lines) - suffix if suffix else len(updated_lines)
    return "\n".join(updated_lines[prefix:end])


def _single_top_k(raw: Any) -> tuple[int, bool]:
    if isinstance(raw, int):
        return raw, False
    if isinstance(raw, list) and raw:
        return int(raw[0]), len(raw) != 1
    return int(raw or 8), raw != 8


def _dedupe_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedupe_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return tuple(out)
