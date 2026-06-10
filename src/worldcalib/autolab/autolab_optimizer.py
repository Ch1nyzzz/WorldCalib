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
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldcalib.benchmark_workspaces import BenchmarkWorkspaceSpec
from worldcalib.optimizer import LocomoOptimizer, OptimizerConfig
from worldcalib.pareto import ParetoPoint, save_frontier
from worldcalib.prediction_feedback import load_task_outcomes
from worldcalib.schemas import CandidateResult
from worldcalib.autolab.autolab import (
    DEFAULT_AUTOLAB_AGENT,
    DEFAULT_AUTOLAB_MODEL,
    DEFAULT_AUTOLAB_SCAFFOLD_NAME,
    DEFAULT_AUTOLAB_TASKS_PATH,
    DEFAULT_HARBOR_BINARY,
    DEFAULT_HARBOR_PYTHON,
    DEFAULT_REWARD_GATE,
    DEFAULT_TERMINUS2_SOURCE,
    AutolabHarborRunner,
    AutolabTask,
    load_autolab_tasks,
    run_autolab_frontier,
)

logger = logging.getLogger(__name__)

# Where, inside a candidate source snapshot, the editable terminus-2 package
# root lives (the parent dir of the importable ``terminus_2`` package). The
# runner puts this dir on PYTHONPATH and loads it via --agent-import-path.
_TERMINUS2_SNAPSHOT_RELROOT = Path("upstream_source") / "terminus2_agent"


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
    terminus2_source_path: Path = DEFAULT_TERMINUS2_SOURCE
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
        self, tasks: list[AutolabTask], *, out_dir: Path, n_attempts: int | None = None
    ) -> AutolabHarborRunner:
        return AutolabHarborRunner(
            tasks=tasks,
            out_dir=out_dir,
            harbor_binary=self.config.harbor_binary,
            harbor_python=self.config.harbor_python,
            harbor_agent=self.config.harbor_agent,
            harbor_model=self.config.harbor_model,
            n_attempts=(n_attempts if n_attempts is not None else self.config.harbor_n_attempts),
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

    # -- editable terminus-2 source snapshot (Option B) ---------------------

    def _terminus2_source_root(self) -> Path:
        """Absolute path to the pristine terminus-2 source root (parent of the
        importable ``terminus_2`` package)."""
        p = Path(self.config.terminus2_source_path)
        return p if p.is_absolute() else (self.project_root / p)

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
        (candidate_dir / "SNAPSHOT_AUTOLAB.md").write_text(
            "\n".join(
                [
                    "# AutoLab agent harness snapshot",
                    "",
                    f"Iteration: {iteration}",
                    "",
                    "You are designing the AGENT HARNESS that AutoLab runs against",
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

        The proposer reports ``extra.source_project_path`` as a free-form string
        and is inconsistent about it: from its sandboxed workspace it often emits
        a doubled / workspace-relative path that does not resolve to a real
        package (run …_160424: 4 of 5 iters emitted a self-doubled path and were
        silently dropped pre-eval). The edited source itself always lands at the
        canonical per-iteration snapshot path the optimizer wrote, so validate
        the emitted path and fall back to that canonical root before giving up to
        the pristine vendored source (= baseline behavior)."""

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

    # -- designer mode (long autonomous session) ---------------------------

    def _build_designer_workspace(self) -> Path:
        """Stage the designer session's workspace.

        Layout (the workspace root is bind-mounted to ``/workspace`` in the
        proposer sandbox; the host eval bridge watches the same dir):

          terminus2_agent/terminus_2/   editable agent package (pristine seed)
          harbor_contract/              read-only interface mirror (reference)
          .worldcalib_tools/{eval,checkpoint,check,done}.py  in-sandbox clients
        """

        ws = self.run_dir / "designer" / "workspace"
        ws.mkdir(parents=True, exist_ok=True)

        src_root = self._terminus2_source_root()
        src_pkg = src_root / "terminus_2"
        if not (src_pkg / "terminus_2.py").is_file():
            raise FileNotFoundError(
                f"terminus-2 seed package not found at {src_pkg}; cannot build a "
                "designer workspace without an editable agent to start from."
            )
        dest_root = ws / "terminus2_agent"
        if dest_root.exists():
            shutil.rmtree(dest_root)
        dest_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            src_pkg,
            dest_root / "terminus_2",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        contract_src = src_root / "harbor_contract"
        if contract_src.is_dir():
            self._copy_tree_if_exists(contract_src, ws / "harbor_contract")

        tools_src = Path(__file__).resolve().parent / "_designer_tools"
        tools_dst = ws / ".worldcalib_tools"
        tools_dst.mkdir(parents=True, exist_ok=True)
        for name in ("eval.py", "checkpoint.py", "check.py", "done.py"):
            shutil.copyfile(tools_src / name, tools_dst / name)
        return ws

    def _designer_base_outcomes(
        self, candidates: list[CandidateResult]
    ) -> dict[str, bool]:
        """Per-task pass/fail of the iter0 baseline, for flip reporting."""
        if not candidates:
            return {}
        base = next(
            (c for c in candidates if c.scaffold_name == DEFAULT_AUTOLAB_SCAFFOLD_NAME),
            candidates[0],
        )
        return load_task_outcomes(Path(base.result_path)) if base.result_path else {}

    def _build_designer_prompt(
        self,
        workspace: Path,
        examples: list[AutolabTask],
        *,
        round_idx: int = 1,
        continuation_reason: str | None = None,
    ) -> str:
        min_dirs = max(1, int(self.config.designer_min_directions))
        task_ids = ", ".join(t.task_id for t in examples)
        head = [
            f"You are a senior research scientist & AI-systems architect. Mission "
            f"(run {self.config.run_id}): design a FUNDAMENTALLY more robust agent "
            "harness for AutoLab, from first principles and from what the traces show "
            "— not to debug the current code. One long self-directed mission; you own "
            "the rhythm and decide when you've converged. Early low scores and "
            "mid-way bugs are fine; only the final harness quality matters.",
            "",
            "Your cwd IS the designer workspace. The editable agent package is at "
            "./terminus2_agent/terminus_2/ (entry class `Terminus2(BaseAgent)` in "
            "terminus_2/terminus_2.py — a reference baseline to SURPASS; keep, rewrite, "
            "or REPLACE IT WHOLESALE). Everything is on the table: change the control "
            "flow / loop topology, add hooks, introduce memory/state, restructure "
            "information flow. The read-only harbor interface mirror is at "
            "./harbor_contract/ — the `BaseAgent` interface is the only fixed point.",
            "",
            f"The train tasks you can evaluate against ({len(examples)}): {task_ids}",
            "",
            "GOAL & STOPPING RULE:",
            f"  Objective: a substantially better harness FRAMEWORK. You decide when no "
            f"more meaningful optimization is worthwhile — BUT you may not stop until "
            f"you have implemented + evaluated + checkpointed >= {min_dirs} GENUINELY "
            f"DIFFERENT architectural directions (decide for yourself what they are; "
            f"do not anchor on any list).",
            "  A prompt-wording or temperature/agent_kwargs tweak is NOT a direction — "
            "such checkpoints are classified `prompt-level` and do NOT count toward the "
            "floor. Make real CODE-LEVEL architectural changes.",
            "  When (and only when) you truly believe you've converged, run "
            '`python .worldcalib_tools/done.py --reason "..."`. If the floor is met it '
            "is honored; otherwise you'll be asked to explore another direction.",
            "",
            "Tools (run from this directory):",
            "  python .worldcalib_tools/check.py                      # FREE syntax+import gate — run after every edit, before any eval",
            "  python .worldcalib_tools/eval.py --tasks <id,id,...>   # your pick of train tasks (n=1 cheap probe)",
            "  python .worldcalib_tools/eval.py --tasks <...> --attempts 2  # noise-reduced CONFIRM before checkpointing",
            "  python .worldcalib_tools/eval.py --subset smoke|train  # shortcuts",
            "  python .worldcalib_tools/eval.py --collect <req_id>     # resume a 'pending' eval",
            '  python .worldcalib_tools/checkpoint.py --note "..." --direction "<tag>" --mechanism "<one line>"',
            '  python .worldcalib_tools/done.py --reason "..."        # declare convergence (subject to the floor)',
            "",
            "Evals are SLOW (~15-60 min/task) and run on real harbor; by default a call "
            "BLOCKS until done. To overlap thinking, submit with `--max-wait 1` then "
            "`--collect`. ALWAYS run check.py after an edit (free) before paying an eval.",
            "",
            "Each eval surfaces, per task, the agent's FULL trajectory at "
            "eval_results/<req_id>__traces/<task_id>.log — READ these to diagnose how "
            "the harness fails and derive your own failure modes (do not assume them). "
            "You also get per-task score / gate pass-fail / flip vs the iter0 baseline. "
            "Keep ./DESIGN_LOG.md as your lab notebook; ./archive.json records each "
            "checkpoint. Use WEB SEARCH to find current state-of-the-art architectures "
            "& papers yourself and adapt the best ideas. Checkpoint every design you'd "
            "want judged — only checkpoints are scored on the held-out test split.",
        ]
        if round_idx > 1 and continuation_reason:
            head = [
                f"[CONTINUATION — round {round_idx}] {continuation_reason}",
                "",
                "Read ./DESIGN_LOG.md and ./archive.json first to recall what you've "
                "already tried; do NOT repeat a direction — pick a genuinely different one.",
                "",
            ] + head
        else:
            head.append("")
            head.append(
                "Start by reading ./harbor_contract/ and "
                "./terminus2_agent/terminus_2/terminus_2.py, run check.py, then probe a "
                "couple of tasks (--tasks <ids>) to see the baseline before designing."
            )
        return "\n".join(head)

    def _designer_distinct_directions(self, checkpoints: list[Any]) -> dict[str, Any]:
        """Count distinct CODE-LEVEL directions (the floor unit). Prompt-level
        checkpoints are recorded but do not count toward '>=N different directions'."""
        code_dirs: dict[str, list[str]] = {}
        for c in checkpoints:
            if getattr(c, "diff_class", "") != "code-level":
                continue
            tag = (getattr(c, "direction_tag", "") or c.ckpt_id).strip().lower()
            code_dirs.setdefault(tag, []).append(c.ckpt_id)
        return {
            "n_distinct_code": len(code_dirs),
            "code_directions": code_dirs,
            "n_prompt_level": sum(
                1 for c in checkpoints if getattr(c, "diff_class", "") == "prompt-level"
            ),
            "n_total_checkpoints": len(checkpoints),
        }

    def _designer_continuation_reason(
        self, converged: bool, dirs: dict[str, Any], min_dirs: int
    ) -> str:
        have = dirs["n_distinct_code"]
        tags = ", ".join(sorted(dirs["code_directions"])) or "(none yet)"
        prompt_only = dirs["n_prompt_level"]
        base = (
            f"You have {have} distinct CODE-LEVEL direction(s) checkpointed so far "
            f"[{tags}]; {prompt_only} prompt-level checkpoint(s) do NOT count. "
            f"The floor is >= {min_dirs} completely different code-level directions."
        )
        if converged:
            return (
                "You declared convergence, but the directions floor is NOT met. "
                + base
                + " Pick a STRUCTURALLY different paradigm you have not tried "
                "(web-search architectures if helpful), implement it as a real "
                "code-level change, eval+checkpoint it, then re-run done.py."
            )
        return (
            "You stopped without declaring convergence. " + base + " Continue: "
            "explore the next genuinely-different code-level direction."
        )

    def _run_designer_session(
        self,
        examples: list[AutolabTask],
        candidates: list[CandidateResult],
    ) -> dict[str, Any]:
        from worldcalib.autolab.eval_bridge import DesignerBudget, EvalBridge
        from worldcalib.prompts import load_proposer_skill

        ws = self._build_designer_workspace()
        designer_dir = self.run_dir / "designer"
        base_outcomes = self._designer_base_outcomes(candidates)
        budget = DesignerBudget(
            max_eval_calls=self.config.designer_max_eval_calls,
            max_task_runs=self.config.designer_max_task_runs,
            max_wall_clock_s=float(self.config.designer_max_wall_clock_s),
        )
        skill = load_proposer_skill("autolab_designer", self._proposer_skill_mode())
        self._deploy_proposer_skill(ws, skill)

        bridge = EvalBridge(
            workspace=ws,
            out_dir=designer_dir,
            runner_factory=(
                lambda tasks, out, n_attempts=None: self._make_harbor_runner(
                    tasks, out_dir=out, n_attempts=n_attempts
                )
            ),
            train_tasks=list(examples),
            base_outcomes=base_outcomes,
            budget=budget,
            baseline_source=self._terminus2_source_root(),
            smoke_task_ids=tuple(self.config.designer_smoke_task_ids),
            smoke_size=self.config.designer_smoke_size,
            event_sink=self._append_event,
        )

        min_dirs = max(1, int(self.config.designer_min_directions))
        max_rounds = max(1, int(self.config.designer_max_rounds))
        converged_path = ws / "CONVERGED.md"

        self._append_event(
            {
                "event": "designer_session_start",
                "workspace": str(ws),
                "n_train_tasks": len(examples),
                "min_directions": min_dirs,
                "max_rounds": max_rounds,
                "budget": budget.snapshot(),
            }
        )
        bridge.start()
        stop_reason = "max_rounds"
        rounds_run = 0
        try:
            continuation_reason: str | None = None
            for rnd in range(1, max_rounds + 1):
                rounds_run = rnd
                # Clear any stale convergence marker before the round.
                if converged_path.exists():
                    converged_path.unlink()
                prompt = self._build_designer_prompt(
                    ws,
                    list(examples),
                    round_idx=rnd,
                    continuation_reason=continuation_reason,
                )
                self._run_proposer_agent(
                    prompt,
                    log_dir=designer_dir / "agent" / f"round_{rnd:02d}",
                    name="designer",
                    cwd=ws,
                    skill_text=skill,
                    sync_calibration_back=False,
                    timeout_s=self.config.designer_session_timeout_s,
                )
                dirs = self._designer_distinct_directions(bridge.checkpoints)
                converged = converged_path.is_file()
                self._append_event(
                    {
                        "event": "designer_round_end",
                        "round": rnd,
                        "converged_declared": converged,
                        **dirs,
                        "budget": budget.snapshot(),
                    }
                )
                if converged and dirs["n_distinct_code"] >= min_dirs:
                    stop_reason = "converged"
                    break
                if budget.exhausted():
                    stop_reason = "budget_ceiling"
                    break
                continuation_reason = self._designer_continuation_reason(
                    converged, dirs, min_dirs
                )
        finally:
            bridge.stop()

        test_summary = self._run_designer_test(bridge.checkpoints, candidates)
        final_summary = {
            "run_id": self.config.run_id,
            "out_dir": str(self.run_dir),
            "mode": "designer",
            "candidate_count": len(candidates),
            "best_candidates_path": str(self.frontier_path),
            "rounds_run": rounds_run,
            "stop_reason": stop_reason,
            "n_checkpoints": len(bridge.checkpoints),
            "directions": self._designer_distinct_directions(bridge.checkpoints),
            "archive_path": str(bridge.archive_path),
            "budget": budget.snapshot(),
            "designer_test": test_summary,
        }
        (self.run_dir / "optimizer_summary.json").write_text(
            json.dumps(final_summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return final_summary

    def _run_designer_test(
        self, checkpoints: list[Any], candidates: list[CandidateResult]
    ) -> dict[str, Any]:
        """Score every checkpoint on the held-out test split and pick a winner.

        This is the harness-controlled, agent-independent measurement: the agent
        never sees the test split and never triggers this eval.
        """

        designer_dir = self.run_dir / "designer"
        designer_dir.mkdir(parents=True, exist_ok=True)
        if not checkpoints:
            summary = {"status": "no_checkpoints", "evaluated_count": 0}
            (designer_dir / "test_results.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._append_event({"event": "designer_no_checkpoints"})
            return summary

        test_tasks = load_autolab_tasks(
            self.config.tasks_path,
            split=self.config.test_split,
            limit=self.config.test_limit,
            task_ids=self.config.task_ids or None,
        )
        test_dir = designer_dir / "test"
        # Held-out selection uses noise-reduced attempts so we don't crown a
        # design that just got a lucky single roll (the optimizer's-curse trap).
        confirm_attempts = max(
            int(self.config.designer_confirm_attempts), int(self.config.harbor_n_attempts)
        )
        runner = self._make_harbor_runner(
            test_tasks, out_dir=test_dir, n_attempts=confirm_attempts
        )

        rows: list[dict[str, Any]] = []
        test_results: list[CandidateResult] = []
        for ck in checkpoints:
            candidate = {
                "name": ck.ckpt_id,
                "agent_source_path": ck.frozen_source_path,
                "scaffold_name": DEFAULT_AUTOLAB_SCAFFOLD_NAME,
                "extra": {"designer_note": ck.note},
            }
            cid = f"designer_test_{ck.ckpt_id}"
            try:
                result = runner.evaluate_candidate(
                    candidate=candidate,
                    candidate_id=cid,
                    agent_name=DEFAULT_AUTOLAB_SCAFFOLD_NAME,
                )
            except Exception as exc:  # noqa: BLE001 - keep testing the rest
                rows.append({"ckpt_id": ck.ckpt_id, "note": ck.note, "error": str(exc)})
                self._append_event(
                    {
                        "event": "designer_test_candidate_failed",
                        "ckpt_id": ck.ckpt_id,
                        "error": str(exc),
                    }
                )
                continue
            test_results.append(result)
            candidates.append(result)
            rows.append(
                {"ckpt_id": ck.ckpt_id, "note": ck.note, "candidate": result.to_dict()}
            )

        winner = (
            max(test_results, key=lambda r: (r.average_score, r.passrate))
            if test_results
            else None
        )
        self._save_best_candidates(candidates)
        self._refresh_run_indexes(candidates)

        summary = {
            "status": "ok" if test_results else "all_failed",
            "split": self.config.test_split,
            "limit": self.config.test_limit,
            "test_task_count": len(test_tasks),
            "n_checkpoints": len(checkpoints),
            "evaluated_count": len(test_results),
            "winner": winner.candidate_id if winner else None,
            "winner_average_score": winner.average_score if winner else None,
            "winner_passrate": winner.passrate if winner else None,
            "test_dir": str(test_dir),
            "rows": rows,
        }
        (designer_dir / "test_results.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._append_event(
            {
                "event": "designer_test_done",
                "winner": summary["winner"],
                "evaluated_count": len(test_results),
            }
        )
        return summary
