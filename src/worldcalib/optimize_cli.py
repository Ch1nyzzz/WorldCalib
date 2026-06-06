"""WorldCalib optimize CLI.

Minimal launcher for `worldcalib-optimize --locomo|--longmemeval`. Covers the
flags actually used in the experiments we care about; everything else falls back
to the LocomoOptimizerConfig / LongMemEvalOptimizerConfig defaults.

Carved from optimizer1.cli.py with all swebench / terminus / graph_colouring /
codex branches stripped. The only WorldCalib-specific addition is the
``--prev-calibration`` flag, which seeds ``runs/<run_id>/world_model_calibration.md``
from a prior run before the loop starts. The proposer reads / appends to that
file via the calibration protocol baked into the per-benchmark SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from worldcalib.memory.locomo_optimizer import LocomoOptimizer, LocomoOptimizerConfig
from worldcalib.memory.longmemeval import (
    DEFAULT_LONGMEMEVAL_JUDGE_BASE_URL,
    DEFAULT_LONGMEMEVAL_JUDGE_MODEL,
    DEFAULT_LONGMEMEVAL_SCAFFOLDS,
)
from worldcalib.memory.longmemeval_optimizer import (
    LongMemEvalOptimizer,
    LongMemEvalOptimizerConfig,
)
# NOTE: agentbench (agentrl) and tau2 optimizers are imported lazily inside their
# task branches — their eval venvs are mutually exclusive (agentbench needs
# agentrl, tau2 needs tau2 and runs in .venv-tau2-eval without agentrl), so a
# top-level import of either would break the other's launcher.
from worldcalib.model import DEFAULT_BASE_URL, DEFAULT_MODEL
from worldcalib.memory.scaffolds import (
    DEFAULT_MEMORY_EVOLUTION_SEED_SCAFFOLDS as DEFAULT_EVOLUTION_SEED_SCAFFOLDS,
)


def _csv(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _scaffold_extra(value: str | None) -> dict[str, dict[str, object]]:
    if not value:
        return {}
    if value.startswith("@"):
        text = Path(value[1:]).read_text(encoding="utf-8")
    else:
        text = value
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("--scaffold-extra-json must decode to an object")
    return parsed


def _load_project_env() -> None:
    """Source ``.env`` (key=value lines) from the project root if present."""

    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _seed_calibration(out_dir: Path, prev_calibration: Path | None) -> None:
    """Bootstrap ``runs/<run_id>/world_model_calibration.md`` before iter 0."""

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "world_model_calibration.md"
    if target.exists():
        return
    if prev_calibration is not None:
        if not prev_calibration.exists():
            raise FileNotFoundError(
                f"--prev-calibration {prev_calibration} does not exist"
            )
        shutil.copy2(prev_calibration, target)
        return
    target.write_text(_BOOTSTRAP_CALIBRATION, encoding="utf-8")


_BOOTSTRAP_CALIBRATION = """\
# World Model Calibration

Append-only. The proposer must read this file before reasoning about the next
candidate, distill any mismatch from the previous iter, then append a new
`## iter_NNN distill` section. Never rewrite or delete prior entries.

## Observability

Each iter produces:
- a per-task answer score (passrate)
- per-task token consumption (prompt + completion)
- traces under `iter_NNN/workspace/traces/`
- failure type distribution recoverable from those traces

There is no hidden / shadow score and no judge that observes generalization.
Train passrate is therefore the only outcome dimension the proposer can predict
against. Do NOT write unfalsifiable generalization judgements into this file —
keep entries to outcome predictions and concrete mismatch observations.
"""


def _add_common_optimize_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--split", default="train")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--eval-timeout-s", type=int, default=300)
    parser.add_argument("--proposer-agent", choices=("claude",), default="claude")
    parser.add_argument("--claude-model", default=None)
    parser.add_argument(
        "--claude-effort",
        choices=("low", "medium", "high", "max"),
        default="high",
    )
    parser.add_argument("--claude-base-url", default=None)
    parser.add_argument("--claude-auth-token", default=None)
    parser.add_argument("--claude-native-auth", action="store_true")
    parser.add_argument("--propose-timeout-s", type=int, default=2400)
    parser.add_argument(
        "--propose-salvage-grace-s",
        type=int,
        default=60,
        help=(
            "Grace window (s) after a docker proposer overruns "
            "--propose-timeout-s: poll for pending_eval.json to finish "
            "flushing, then docker kill the orphaned container."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-context-chars", type=int, default=6000)
    parser.add_argument("--eval-workers", type=int, default=64)
    parser.add_argument("--skip-scaffold-eval", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--scaffolds", default=None)
    parser.add_argument("--scaffold-extra-json", default=None)
    parser.add_argument(
        "--selection-policy",
        default="default",
        help="Optimizer1 selection policy (default, progressive, bandit, pareto, island, ...)",
    )
    parser.add_argument(
        "--island-explore-c",
        type=float,
        default=0.5,
        help=(
            "UCB1 exploration weight for the 'island' selection policy. "
            "Higher = more exploration (under-expanded leaders + clean seed); "
            "lower = greedier toward the current passrate champion."
        ),
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=None,
        help=(
            "Path to a precomputed iter-0 baseline run dir; reused as the "
            "starting frontier so we don't repay the baseline eval."
        ),
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help=(
            "Withhold the upstream cumulative summary directory from the "
            "proposer's workspace (matches Optimizer1's --no-summary)."
        ),
    )
    parser.add_argument(
        "--proposer-sandbox",
        choices=("none", "docker"),
        default="none",
        help="Run proposer natively (none) or inside a docker container.",
    )
    parser.add_argument("--proposer-docker-image", default="")
    parser.add_argument("--proposer-docker-user", default="")
    parser.add_argument("--proposer-docker-home", default="")
    parser.add_argument(
        "--proposer-docker-env",
        action="append",
        default=[],
        help="Env var name to forward into the proposer container. Repeatable.",
    )
    parser.add_argument(
        "--proposer-docker-mount",
        action="append",
        default=[],
        help="Additional docker mount (HOST:CONTAINER[:MODE]). Repeatable.",
    )
    parser.add_argument(
        "--prev-calibration",
        type=Path,
        default=None,
        help=(
            "Path to a previous run's world_model_calibration.md to seed this run. "
            "If omitted, the run starts with the bootstrap template. "
            "Ignored when --proposer-variant=critic (that variant has no prose file)."
        ),
    )
    parser.add_argument(
        "--proposer-variant",
        choices=("prose", "critic", "calib", "nowmc"),
        default="prose",
        help=(
            "Proposer world-model variant. 'prose' = append-only "
            "world_model_calibration.md protocol (default). 'critic' = ledger + "
            "adversarial reference-class critic subagent. 'calib' = prose WMC + a "
            "two-sided prediction graded after eval by an external critic "
            "(prediction accuracy becomes an optimized scalar; routes to the "
            "<benchmark>_calib skill). 'nowmc' = pure-default ablation with NO "
            "calibration protocol of any kind (no prose file, no prediction, no "
            "critic; routes to the <benchmark>_nowmc skill)."
        ),
    )
    parser.add_argument(
        "--critic-gate-enforce",
        action="store_true",
        help=(
            "Critic variant only: reject a candidate that did not produce a "
            "compliant critique.md / P(regress). Default off (soft): compliance "
            "is logged but the candidate is still evaluated."
        ),
    )
    parser.add_argument(
        "--dry-run-probe-k",
        type=int,
        default=0,
        help=(
            "Before the full eval, smoke-run each candidate on this many probe "
            "tasks; if it produces zero model output on all of them (a runtime "
            "crash), skip it instead of burning a full eval. 0 disables (default)."
        ),
    )
    parser.add_argument(
        "--fanout-k",
        type=int,
        default=1,
        help=(
            "Fan-out best-of-N (calib variant only). When > 1, each iteration "
            "spawns this many proposer agents IN PARALLEL — each independently "
            "designs and fully implements ONE candidate — then an independent "
            "orchestrator selects the single winner to evaluate. 1 = classic "
            "single-proposer path (default). Eval cost stays at one candidate."
        ),
    )
    parser.add_argument(
        "--no-fanout-orchestrator",
        dest="fanout_orchestrator",
        action="store_false",
        help=(
            "With --fanout-k>1, skip the orchestrator agent and select the "
            "winner by a deterministic risk-adjusted rule (strongest net "
            "lower bound) over the proposers' self-predictions. Control arm."
        ),
    )
    parser.set_defaults(fanout_orchestrator=True)
    parser.add_argument(
        "--bestofn-k",
        type=int,
        default=1,
        help=(
            "Best-of-N single-proposer (calib variant only). When > 1, ONE "
            "proposer designs and fully implements this many distinct "
            "candidates in a single workspace (each under ./cand_<i>/), writes "
            "a prediction per candidate, and an independent selector (the same "
            "orchestrator agent, gated by --no-fanout-orchestrator) picks the "
            "one to evaluate. Differs from --fanout-k (K parallel agents) by "
            "using one proposer. 1 = classic single-candidate path (default)."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldcalib-optimize",
        description=(
            "Run one optimization loop with the WorldCalib calibration protocol. "
            "Exactly one of --locomo / --longmemeval must be set."
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--locomo", dest="task", action="store_const", const="locomo")
    target.add_argument(
        "--longmemeval", dest="task", action="store_const", const="longmemeval"
    )
    target.add_argument(
        "--agentbench", dest="task", action="store_const", const="agentbench"
    )
    target.add_argument("--tau2", dest="task", action="store_const", const="tau2")
    target.add_argument(
        "--arc-agi2", dest="task", action="store_const", const="arc_agi2"
    )
    target.add_argument(
        "--swebench", dest="task", action="store_const", const="swebench"
    )
    target.add_argument(
        "--autolab", dest="task", action="store_const", const="autolab"
    )

    _add_common_optimize_args(parser)

    parser.add_argument("--longmemeval-variant", choices=("s", "m", "oracle"), default="s")
    parser.add_argument("--longmemeval-data-path", type=Path, default=None)
    parser.add_argument("--longmemeval-split-path", type=Path, default=None)
    parser.add_argument("--longmemeval-question-types", default="")
    parser.add_argument(
        "--longmemeval-judge-model", default=DEFAULT_LONGMEMEVAL_JUDGE_MODEL
    )
    parser.add_argument(
        "--longmemeval-judge-base-url", default=DEFAULT_LONGMEMEVAL_JUDGE_BASE_URL
    )
    parser.add_argument("--longmemeval-judge-api-key", default=None)
    parser.add_argument("--longmemeval-judge-timeout-s", type=int, default=300)
    parser.add_argument("--longmemeval-no-llm-judge", action="store_true")

    parser.add_argument(
        "--agentbench-task",
        choices=("db", "os", "alfworld", "webshop"),
        default="db",
    )
    parser.add_argument("--controller-url", default="http://localhost:5020/api")
    parser.add_argument("--agentbench-runs", type=int, default=1)
    parser.add_argument("--agentbench-concurrency", type=int, default=8)
    # Default train split kept small (30): tasks without a dataset task-type
    # (os/webshop/alfworld) are predicted per episode, which only stays tractable
    # at a small episode count. db has task-types; raise this if running db wide.
    parser.add_argument("--agentbench-train-size", type=int, default=30)
    parser.add_argument("--agentbench-test-size", type=int, default=40)

    parser.add_argument(
        "--tau2-domain",
        choices=("telecom", "airline", "retail", "banking_knowledge"),
        default="telecom",
    )
    parser.add_argument("--tau2-agent-model", default="deepseek/deepseek-chat")
    parser.add_argument("--tau2-user-model", default="deepseek/deepseek-chat")
    parser.add_argument("--tau2-agent-temperature", type=float, default=0.0)
    parser.add_argument("--tau2-user-temperature", type=float, default=0.0)
    parser.add_argument("--tau2-max-steps", type=int, default=200)
    parser.add_argument("--tau2-runs", type=int, default=1)
    parser.add_argument("--tau2-concurrency", type=int, default=4)
    parser.add_argument("--tau2-train-size", type=int, default=40)
    parser.add_argument("--tau2-test-size", type=int, default=40)
    parser.add_argument("--tau2-pass-threshold", type=float, default=1.0)
    parser.add_argument("--tau2-request-timeout-s", type=int, default=120)
    parser.add_argument("--tau2-num-retries", type=int, default=2)

    parser.add_argument(
        "--arc-data-dir", default="/data/home/yuhan/ARC-AGI-2/data"
    )
    parser.add_argument("--arc-train-size", type=int, default=40)
    parser.add_argument("--arc-test-size", type=int, default=40)
    parser.add_argument("--arc-max-tokens", type=int, default=2048)
    parser.add_argument("--arc-max-attempts", type=int, default=2)
    parser.add_argument("--arc-runs", type=int, default=1)
    parser.add_argument("--arc-concurrency", type=int, default=8)

    parser.add_argument("--swebench-data-path", type=Path, default=None)
    # Default None -> the swebench dispatch branch falls back to
    # SwebenchOptimizerConfig.mini_swe_agent_source_path so we avoid a
    # top-level import of the coding module here.
    parser.add_argument("--mini-swe-agent-source-path", type=Path, default=None)
    parser.add_argument("--mini-swe-agent-command", default="")
    parser.add_argument("--mini-swe-agent-eval-command", default="")
    parser.add_argument("--swebench-force", action="store_true")

    parser.add_argument(
        "--autolab-tasks-path",
        type=Path,
        default=None,
        help="Path to the AutoLab 36-task dir (default: third_party/autolab/tasks).",
    )
    parser.add_argument(
        "--autolab-terminus2-source",
        type=Path,
        default=None,
        help=(
            "Editable terminus-2 source root (parent of the terminus_2/ package) "
            "the proposer snapshots and edits. Default: references/vendor/terminus2_agent."
        ),
    )
    parser.add_argument("--autolab-harbor-python", type=Path, default=None)
    parser.add_argument("--autolab-harbor-binary", type=Path, default=None)
    parser.add_argument("--autolab-agent", default="terminus-2")
    parser.add_argument("--autolab-harbor-model", default=None)
    parser.add_argument("--autolab-n-attempts", type=int, default=1)
    parser.add_argument("--autolab-timeout-multiplier", type=float, default=1.0)
    parser.add_argument("--autolab-concurrency", type=int, default=4)
    parser.add_argument("--autolab-env-file", type=Path, default=None)
    parser.add_argument("--autolab-reward-gate", type=float, default=0.5)
    parser.add_argument(
        "--autolab-score-mode",
        choices=("best", "avg"),
        default="best",
        help="Which of Best@k / Avg@k drives TaskResult.score (default best).",
    )
    parser.add_argument(
        "--autolab-task-ids",
        default="",
        help="Comma-separated subset of task ids; empty = all 36.",
    )
    parser.add_argument("--autolab-force", action="store_true")
    parser.add_argument(
        "--autolab-skip-patch-check",
        dest="autolab_verify_patches",
        action="store_false",
        help=(
            "Skip the startup check that the cyh_dev harbor is patched for "
            "GPU passthrough + long command durations. Off-by-default; only "
            "use when running CPU-only tasks on an intentionally-unpatched venv."
        ),
    )
    parser.set_defaults(autolab_verify_patches=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _load_project_env()

    run_id = args.run_id or (
        f"wc_{args.task}_{os.getpid()}"
        if not args.out
        else args.out.name
    )
    out_dir = args.out or Path("runs") / run_id

    # The critic and nowmc variants have no prose calibration file to seed.
    if args.proposer_variant not in ("critic", "nowmc"):
        _seed_calibration(out_dir, args.prev_calibration)

    if args.scaffolds:
        scaffolds_csv = _csv(args.scaffolds)
    elif args.task == "longmemeval":
        scaffolds_csv = list(DEFAULT_LONGMEMEVAL_SCAFFOLDS)
    elif args.task == "agentbench":
        from worldcalib.agentic.backends.agentbench import (
            DEFAULT_AGENT_SEED_SCAFFOLDS,
        )

        scaffolds_csv = list(DEFAULT_AGENT_SEED_SCAFFOLDS)
    elif args.task == "tau2":
        from worldcalib.agentic.backends.tau2 import DEFAULT_TAU2_SEED_SCAFFOLDS

        scaffolds_csv = list(DEFAULT_TAU2_SEED_SCAFFOLDS)
    elif args.task == "arc_agi2":
        from worldcalib.reasoning.arc_scaffolds import DEFAULT_ARC_SEED_SCAFFOLDS

        scaffolds_csv = list(DEFAULT_ARC_SEED_SCAFFOLDS)
    elif args.task == "swebench":
        from worldcalib.coding.swebench import DEFAULT_MINI_SWE_AGENT_NAME

        scaffolds_csv = [DEFAULT_MINI_SWE_AGENT_NAME]
    elif args.task == "autolab":
        from worldcalib.autolab.autolab import DEFAULT_AUTOLAB_SCAFFOLD_NAME

        scaffolds_csv = [DEFAULT_AUTOLAB_SCAFFOLD_NAME]
    else:
        scaffolds_csv = list(DEFAULT_EVOLUTION_SEED_SCAFFOLDS)
    scaffold_extra = _scaffold_extra(args.scaffold_extra_json)

    shared = dict(
        run_id=run_id,
        out_dir=out_dir,
        iterations=args.iterations,
        split=args.split,
        limit=args.limit,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        eval_timeout_s=args.eval_timeout_s,
        proposer_agent=args.proposer_agent,
        claude_model=args.claude_model,
        claude_effort=args.claude_effort,
        claude_base_url=args.claude_base_url,
        claude_auth_token=args.claude_auth_token,
        claude_native_auth=args.claude_native_auth,
        propose_timeout_s=args.propose_timeout_s,
        propose_salvage_grace_s=args.propose_salvage_grace_s,
        dry_run=args.dry_run,
        max_context_chars=args.max_context_chars,
        max_eval_workers=args.eval_workers,
        skip_scaffold_eval=args.skip_scaffold_eval,
        resume=args.resume,
        scaffolds=tuple(scaffolds_csv),
        scaffold_extra=scaffold_extra,
        selection_policy=args.selection_policy,
        island_explore_c=args.island_explore_c,
        baseline_dir=args.baseline_dir,
        summaries_in_workspace=not args.no_summary,
        proposer_sandbox=args.proposer_sandbox,
        proposer_docker_image=args.proposer_docker_image,
        proposer_docker_user=args.proposer_docker_user,
        proposer_docker_home=args.proposer_docker_home,
        proposer_docker_env=tuple(args.proposer_docker_env),
        proposer_docker_mount=tuple(args.proposer_docker_mount),
        proposer_variant=args.proposer_variant,
        critic_gate_enforce=args.critic_gate_enforce,
        dry_run_probe_k=args.dry_run_probe_k,
        fanout_k=args.fanout_k,
        fanout_orchestrator=args.fanout_orchestrator,
        bestofn_k=args.bestofn_k,
    )

    if args.task == "longmemeval":
        optimizer = LongMemEvalOptimizer(
            LongMemEvalOptimizerConfig(
                **shared,
                dataset_variant=args.longmemeval_variant,
                data_path=args.longmemeval_data_path,
                split_path=args.longmemeval_split_path,
                question_types=tuple(_csv(args.longmemeval_question_types)),
                judge_model=args.longmemeval_judge_model,
                judge_base_url=args.longmemeval_judge_base_url,
                judge_api_key=args.longmemeval_judge_api_key,
                judge_timeout_s=args.longmemeval_judge_timeout_s,
                use_llm_judge=not args.longmemeval_no_llm_judge,
            )
        )
    elif args.task == "agentbench":
        from worldcalib.agentic.backends.agentbench.optimizer import (
            AgentBenchOptimizer,
            AgentBenchOptimizerConfig,
        )

        optimizer = AgentBenchOptimizer(
            AgentBenchOptimizerConfig(
                **shared,
                agentbench_task=args.agentbench_task,
                controller_url=args.controller_url,
                agentbench_runs=args.agentbench_runs,
                agentbench_concurrency=args.agentbench_concurrency,
                agentbench_train_size=args.agentbench_train_size,
                agentbench_test_size=args.agentbench_test_size,
            )
        )
    elif args.task == "tau2":
        from worldcalib.agentic.backends.tau2.optimizer import (
            Tau2Optimizer,
            Tau2OptimizerConfig,
        )

        optimizer = Tau2Optimizer(
            Tau2OptimizerConfig(
                **shared,
                tau2_domain=args.tau2_domain,
                tau2_agent_model=args.tau2_agent_model,
                tau2_user_model=args.tau2_user_model,
                tau2_agent_temperature=args.tau2_agent_temperature,
                tau2_user_temperature=args.tau2_user_temperature,
                tau2_max_steps=args.tau2_max_steps,
                tau2_runs=args.tau2_runs,
                tau2_concurrency=args.tau2_concurrency,
                tau2_train_size=args.tau2_train_size,
                tau2_test_size=args.tau2_test_size,
                tau2_pass_threshold=args.tau2_pass_threshold,
                tau2_request_timeout_s=args.tau2_request_timeout_s,
                tau2_num_retries=args.tau2_num_retries,
            )
        )
    elif args.task == "arc_agi2":
        from worldcalib.reasoning.arc_optimizer import (
            ArcOptimizer,
            ArcOptimizerConfig,
        )

        optimizer = ArcOptimizer(
            ArcOptimizerConfig(
                **shared,
                arc_data_dir=args.arc_data_dir,
                arc_train_size=args.arc_train_size,
                arc_test_size=args.arc_test_size,
                arc_max_tokens=args.arc_max_tokens,
                arc_max_attempts=args.arc_max_attempts,
                arc_runs=args.arc_runs,
                arc_concurrency=args.arc_concurrency,
            )
        )
    elif args.task == "swebench":
        from worldcalib.coding.swebench_optimizer import (
            SwebenchOptimizer,
            SwebenchOptimizerConfig,
        )

        # mini_swe_agent_source_path falls back to the config default
        # (DEFAULT_MINI_SWE_AGENT_SOURCE_PATH) when the flag is omitted.
        swebench_kwargs = dict(
            **shared,
            data_path=args.swebench_data_path,
            mini_swe_agent_command=args.mini_swe_agent_command,
            mini_swe_agent_eval_command=args.mini_swe_agent_eval_command,
            force=args.swebench_force,
        )
        if args.mini_swe_agent_source_path is not None:
            swebench_kwargs["mini_swe_agent_source_path"] = (
                args.mini_swe_agent_source_path
            )
        optimizer = SwebenchOptimizer(SwebenchOptimizerConfig(**swebench_kwargs))
    elif args.task == "autolab":
        from worldcalib.autolab.autolab_optimizer import (
            AutolabOptimizer,
            AutolabOptimizerConfig,
        )

        # Path-typed flags fall back to AutolabOptimizerConfig defaults when
        # omitted, so we avoid a top-level import of the autolab module here.
        autolab_kwargs = dict(
            **shared,
            harbor_agent=args.autolab_agent,
            harbor_n_attempts=args.autolab_n_attempts,
            harbor_timeout_multiplier=args.autolab_timeout_multiplier,
            harbor_concurrency=args.autolab_concurrency,
            reward_gate=args.autolab_reward_gate,
            score_mode=args.autolab_score_mode,
            task_ids=tuple(_csv(args.autolab_task_ids)),
            force=args.autolab_force,
            verify_patches=args.autolab_verify_patches,
        )
        if args.autolab_tasks_path is not None:
            autolab_kwargs["tasks_path"] = args.autolab_tasks_path
        if args.autolab_terminus2_source is not None:
            autolab_kwargs["terminus2_source_path"] = args.autolab_terminus2_source
        if args.autolab_harbor_python is not None:
            autolab_kwargs["harbor_python"] = args.autolab_harbor_python
        if args.autolab_harbor_binary is not None:
            autolab_kwargs["harbor_binary"] = args.autolab_harbor_binary
        if args.autolab_harbor_model is not None:
            autolab_kwargs["harbor_model"] = args.autolab_harbor_model
        if args.autolab_env_file is not None:
            autolab_kwargs["harbor_env_file"] = args.autolab_env_file
        optimizer = AutolabOptimizer(AutolabOptimizerConfig(**autolab_kwargs))
    else:
        optimizer = LocomoOptimizer(LocomoOptimizerConfig(**shared))

    payload = optimizer.run()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
