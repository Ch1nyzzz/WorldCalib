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

Goal: a falsifiable MODEL OF THE ENVIRONMENT (how the SUT behaves as an agent,
how the tools/eval/tasks behave) — a patch is an experiment that tests and
exploits it. Passrate is the downstream consequence; the model is the object you
maintain. Each iteration is one experiment: predict → observe → correct.

This file has two regions, split at the first `## iter_` heading:
- **HEAD (mutable, rewritten in place each iter)** — the live model below.
- **HISTORY (append-only, from the first `## iter_` on)** — one distill block per
  iter; never edit or delete a prior block. The harness keeps HISTORY from shrinking.

Each iter: rewrite the HEAD to current state, then append one distill block. Keep
it lean — prefer 5 high-confidence beliefs over 20 vague ones. Start the Beliefs
list EMPTY and fill it only from this run's evidence; never pre-seed guessed
failure modes.

## Beliefs
Falsifiable facts (rewrite in place; bootstrap them from the seed traces at iter 1):
`[E<n>] <claim> | conf:<0-1> | status:<hypothesis|confirmed|refuted> | evidence:<trace ids / tool-call outputs> | mass:~<N>`

## Experiments
What has been tried against each belief, so a spent direction is never re-run:
`- <belief E<n>>: <experiment> → <held|flat|harmful>`

## Calibration
How well recent predictions held (the meta-signal for the next experiment):
- prediction hit-rate: behavioral 0/0, aggregate 0/0
- state: no beliefs yet — first experiments buy information

## iter_000 -> iter_001 distill (bootstrap)
- Experiment: bootstrap
- note: seed Beliefs from the seed traces at iter 1 (as `hypothesis`); read
  behavioral evidence from trace turns / tool-call outputs, stable-vs-unstable
  from `task_score_matrix.json`.
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
    parser.add_argument(
        "--proposer-agent", choices=("claude", "codex"), default="claude"
    )
    parser.add_argument("--claude-model", default=None)
    parser.add_argument(
        "--claude-effort",
        choices=("low", "medium", "high", "max"),
        default="high",
    )
    parser.add_argument("--claude-base-url", default=None)
    parser.add_argument("--claude-auth-token", default=None)
    parser.add_argument("--claude-native-auth", action="store_true")
    # Codex proposer (used only with --proposer-agent codex). Auth comes from
    # $CODEX_HOME/auth.json, so there is no token flag.
    parser.add_argument("--codex-model", default="gpt-5.6-sol")
    parser.add_argument(
        "--codex-reasoning-effort",
        choices=("low", "medium", "high", "xhigh"),
        default="xhigh",
    )
    parser.add_argument("--codex-home", default="")
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
        choices=("self", "default"),
        default="self",
        help=(
            "Patch-base policy. 'self' (default): the lex-best candidate "
            "(passrate, then average_score) is materialised as the default "
            "base and the PROPOSER decides what to build on, guided by "
            "frontier_manifest.json + task_score_matrix.json. 'default': "
            "always re-baseline from the clean seed snapshot."
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
            "Ignored when --proposer-variant=nowmc (no calibration file)."
        ),
    )
    parser.add_argument(
        "--proposer-variant",
        choices=("calib", "nowmc"),
        default="calib",
        help=(
            "Proposer world-model variant. 'calib' (default) = self-distill "
            "WMC: append-only world_model_calibration.md + a per-task "
            "prediction.md the proposer self-grades next iter (no external "
            "critic; routes to the <benchmark>_calib skill). 'nowmc' = "
            "pure-default ablation with NO calibration protocol of any kind "
            "(routes to the <benchmark>_nowmc skill)."
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
    target.add_argument("--gaia", dest="task", action="store_const", const="gaia")
    target.add_argument(
        "--arc-agi2", dest="task", action="store_const", const="arc_agi2"
    )
    target.add_argument(
        "--swebench", dest="task", action="store_const", const="swebench"
    )
    target.add_argument(
        "--autolab", dest="task", action="store_const", const="autolab"
    )
    target.add_argument("--tb2", dest="task", action="store_const", const="tb2")
    target.add_argument(
        "--spider2", dest="task", action="store_const", const="spider2"
    )
    target.add_argument(
        "--toolathlon", dest="task", action="store_const", const="toolathlon"
    )
    target.add_argument(
        "--appworld", dest="task", action="store_const", const="appworld"
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
    # Target-model sampling temperature (agentrl's own default is 0.8 — noisy).
    parser.add_argument("--agentbench-temperature", type=float, default=0.0)

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

    # GAIA (L1+L2 by default; exact-match graded; FC agent over deepseek SUT)
    parser.add_argument(
        "--gaia-levels",
        default="1,2",
        help="CSV of GAIA difficulty levels to include (default 1,2).",
    )
    parser.add_argument("--gaia-runs", type=int, default=1)
    parser.add_argument("--gaia-concurrency", type=int, default=8)
    parser.add_argument("--gaia-train-size", type=int, default=40)
    parser.add_argument("--gaia-test-size", type=int, default=0)

    parser.add_argument(
        "--arc-data-dir", default="/data/home/yuhan/ARC-AGI-2/data"
    )
    parser.add_argument("--arc-train-size", type=int, default=40)
    parser.add_argument("--arc-test-size", type=int, default=40)
    parser.add_argument("--arc-max-tokens", type=int, default=2048)
    parser.add_argument("--arc-max-attempts", type=int, default=2)
    parser.add_argument("--arc-runs", type=int, default=1)
    parser.add_argument("--arc-concurrency", type=int, default=8)

    # Spider2-lite local (sqlite) subset; execution-graded single-shot text-to-SQL
    # over the deepseek SUT. Frozen db-disjoint split data/spider2/lite_local_split.json
    # owns the train/test instance ids (31 train / 104 test).
    parser.add_argument("--spider2-runs", type=int, default=1)
    parser.add_argument("--spider2-concurrency", type=int, default=8)

    # Toolathlon: containerized multi-app tool-use benchmark, end-state graded via
    # the benchmark's own run_parallel.py. Frozen app-disjoint split
    # data/toolathlon/finalpool_split.json owns the train/test ids (28 train /
    # 72 test; 8 cred/env-blocked tasks excluded). SUT locked to deepseek-v4-flash.
    parser.add_argument("--toolathlon-concurrency", type=int, default=8)
    parser.add_argument("--toolathlon-maxstep", type=int, default=50)
    parser.add_argument("--toolathlon-per-task-timeout-s", type=int, default=1800)
    parser.add_argument("--toolathlon-root", type=Path, default=None)
    parser.add_argument("--toolathlon-force", action="store_true")

    # AppWorld: external-runner interactive coding-agent benchmark, eval in the
    # isolated .venv-appworld (subprocess-harvest). Frozen split
    # data/appworld/split.json owns train (train[:50]) / test (test_normal, 168).
    # SUT locked to deepseek-v4-flash.
    parser.add_argument("--appworld-concurrency", type=int, default=64)
    parser.add_argument("--appworld-max-interactions", type=int, default=100)
    parser.add_argument("--appworld-per-task-timeout-s", type=int, default=600)
    parser.add_argument(
        "--appworld-repeats", type=int, default=1,
        help="k-times averaging: evaluate each task k times and use the MEAN "
             "pass-rate as the reward (shrinks deepseek temp-0 MoE eval noise ~sqrt(k)).",
    )
    parser.add_argument("--appworld-force", action="store_true")

    parser.add_argument("--swebench-data-path", type=Path, default=None)
    # Default None -> the swebench dispatch branch falls back to
    # SwebenchOptimizerConfig.mini_swe_agent_source_path so we avoid a
    # top-level import of the coding module here.
    parser.add_argument("--mini-swe-agent-source-path", type=Path, default=None)
    parser.add_argument("--mini-swe-agent-command", default="")
    parser.add_argument("--mini-swe-agent-eval-command", default="")
    parser.add_argument("--swebench-force", action="store_true")

    parser.add_argument(
        "--tb2-dataset",
        type=Path,
        default=None,
        help="Path to the Terminal-Bench 2.0 Harbor dataset dir (89 task dirs).",
    )
    parser.add_argument(
        "--tb2-terminus2-source",
        type=Path,
        default=None,
        help=(
            "Editable terminus-2 source root the proposer snapshots and edits. "
            "Default: references/vendor/terminus2_agent_tb2 — tb2's own copy, so "
            "candidate edits never reach the AutoLab experiments."
        ),
    )
    parser.add_argument("--tb2-harbor-python", type=Path, default=None)
    parser.add_argument("--tb2-harbor-binary", type=Path, default=None)
    parser.add_argument("--tb2-agent", default=None)
    parser.add_argument(
        "--tb2-harbor-model",
        default=None,
        help="Frozen SUT. Default: the GPUGeek-served DeepSeek-V4-Flash.",
    )
    parser.add_argument(
        "--tb2-api-base",
        default=None,
        help="Solver endpoint handed to terminus-2 as the api_base agent kwarg.",
    )
    parser.add_argument(
        "--tb2-repeats",
        type=int,
        default=None,
        help=(
            "Trials per task. Terminal-Bench's published metric is pass@1 averaged "
            "over repeats with MEAN; the default is 2."
        ),
    )
    parser.add_argument(
        "--tb2-concurrency",
        type=int,
        default=None,
        help=(
            "Concurrent trials (default 8). Each takes its own Docker compose "
            "network and the host pool holds ~31 in total; 16 has been measured "
            "exhausting it and failing 19 of 20 tasks."
        ),
    )
    parser.add_argument("--tb2-timeout-multiplier", type=float, default=None)
    parser.add_argument("--tb2-max-turns", type=int, default=None)
    parser.add_argument("--tb2-max-task-minutes", type=float, default=None)
    parser.add_argument("--tb2-env-file", type=Path, default=None)
    parser.add_argument(
        "--tb2-harbor-environment",
        default=None,
        help=(
            "harbor -e: trial sandbox backend (docker|daytona|e2b|modal|...). "
            "Default: harbor's own default (local docker). daytona needs "
            "DAYTONA_API_KEY in the environment and uses each task's prebuilt "
            "image remotely, freeing the host docker network pool."
        ),
    )
    parser.add_argument("--tb2-task-ids", default="")
    parser.add_argument("--tb2-force", action="store_true")

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
    parser.add_argument(
        "--autolab-max-turns",
        type=int,
        default=0,
        help=(
            "Hard cap on the terminus-2 agent episode loop (injected as "
            "--ak max_turns). 0 = no cap. Bounds a candidate whose finalization "
            "gate keeps rejecting task_complete from looping indefinitely."
        ),
    )
    parser.add_argument(
        "--autolab-max-task-minutes",
        type=float,
        default=0.0,
        help=(
            "Absolute per-task agent wall-clock ceiling in minutes, applied "
            "gracefully via harbor's --agent-timeout-multiplier. 0 = no cap. "
            "Only tasks whose native agent timeout exceeds this are shortened."
        ),
    )
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

    # --- Designer mode (AutoLab only): one long autonomous session ----------
    parser.add_argument(
        "--designer",
        action="store_true",
        help=(
            "AutoLab only: run ONE long autonomous designer session (the agent "
            "owns the rhythm, calls worldcalib-eval on demand, checkpoints "
            "designs) instead of the per-iteration loop. --iterations is ignored."
        ),
    )
    parser.add_argument(
        "--designer-session-timeout-s",
        type=int,
        default=4 * 3600,
        help="PER-ROUND inner-agent timeout for the designer goal-loop.",
    )
    parser.add_argument(
        "--designer-min-directions",
        type=int,
        default=3,
        help="Hard floor: the designer may not stop until it has implemented+"
        "evaluated+checkpointed this many genuinely-different CODE-LEVEL directions.",
    )
    parser.add_argument(
        "--designer-max-rounds",
        type=int,
        default=6,
        help="Max continuation rounds (re-invocations) of the designer goal-loop.",
    )
    parser.add_argument(
        "--designer-confirm-attempts",
        type=int,
        default=2,
        help="harbor -k used for held-out checkpoint selection (noise reduction).",
    )
    parser.add_argument(
        "--designer-max-eval-calls",
        type=int,
        default=40,
        help="Max number of eval submissions the designer agent may make.",
    )
    parser.add_argument(
        "--designer-max-task-runs",
        type=int,
        default=120,
        help="Max cumulative harbor task-runs across all designer evals (the cost cap).",
    )
    parser.add_argument("--designer-max-wall-clock-s", type=int, default=6 * 3600)
    parser.add_argument(
        "--designer-smoke-task-ids",
        default="",
        help="CSV of train task ids for the `--subset smoke` shortcut (default: a few CPU-only train tasks).",
    )
    parser.add_argument("--designer-smoke-size", type=int, default=3)

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

    # The nowmc variant has no calibration file to seed.
    if args.proposer_variant != "nowmc":
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
    elif args.task == "gaia":
        from worldcalib.agentic.backends.gaia import DEFAULT_GAIA_SEED_SCAFFOLDS

        scaffolds_csv = list(DEFAULT_GAIA_SEED_SCAFFOLDS)
    elif args.task == "arc_agi2":
        from worldcalib.reasoning.arc_scaffolds import DEFAULT_ARC_SEED_SCAFFOLDS

        scaffolds_csv = list(DEFAULT_ARC_SEED_SCAFFOLDS)
    elif args.task == "swebench":
        from worldcalib.coding.swebench import DEFAULT_MINI_SWE_AGENT_NAME

        scaffolds_csv = [DEFAULT_MINI_SWE_AGENT_NAME]
    elif args.task == "autolab":
        from worldcalib.autolab.autolab import DEFAULT_AUTOLAB_SCAFFOLD_NAME

        scaffolds_csv = [DEFAULT_AUTOLAB_SCAFFOLD_NAME]
    elif args.task == "tb2":
        from worldcalib.tb2.tb2 import DEFAULT_TB2_SCAFFOLD_NAME

        scaffolds_csv = [DEFAULT_TB2_SCAFFOLD_NAME]
    elif args.task == "spider2":
        from worldcalib.agentic.backends.spider2 import (
            DEFAULT_SPIDER2_SEED_SCAFFOLDS,
        )

        scaffolds_csv = list(DEFAULT_SPIDER2_SEED_SCAFFOLDS)
    elif args.task == "toolathlon":
        from worldcalib.agentic.backends.toolathlon import (
            DEFAULT_TOOLATHLON_SEED_SCAFFOLDS,
        )

        scaffolds_csv = list(DEFAULT_TOOLATHLON_SEED_SCAFFOLDS)
    elif args.task == "appworld":
        from worldcalib.agentic.backends.appworld import (
            DEFAULT_APPWORLD_SEED_SCAFFOLDS,
        )

        scaffolds_csv = list(DEFAULT_APPWORLD_SEED_SCAFFOLDS)
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
        codex_model=args.codex_model,
        codex_reasoning_effort=args.codex_reasoning_effort,
        codex_home=args.codex_home,
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
        baseline_dir=args.baseline_dir,
        summaries_in_workspace=not args.no_summary,
        proposer_sandbox=args.proposer_sandbox,
        proposer_docker_image=args.proposer_docker_image,
        proposer_docker_user=args.proposer_docker_user,
        proposer_docker_home=args.proposer_docker_home,
        proposer_docker_env=tuple(args.proposer_docker_env),
        proposer_docker_mount=tuple(args.proposer_docker_mount),
        proposer_variant=args.proposer_variant,
        dry_run_probe_k=args.dry_run_probe_k,
        designer=args.designer,
        designer_min_directions=args.designer_min_directions,
        designer_max_rounds=args.designer_max_rounds,
        designer_confirm_attempts=args.designer_confirm_attempts,
        designer_session_timeout_s=args.designer_session_timeout_s,
        designer_max_eval_calls=args.designer_max_eval_calls,
        designer_max_task_runs=args.designer_max_task_runs,
        designer_max_wall_clock_s=args.designer_max_wall_clock_s,
        designer_smoke_task_ids=tuple(_csv(args.designer_smoke_task_ids)),
        designer_smoke_size=args.designer_smoke_size,
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
                agentbench_temperature=args.agentbench_temperature,
                # The runner samples the SUT off deepseek_model/deepseek_base_url,
                # NOT the shared model/base_url — so --model/--base-url were
                # silently ignored for agentbench (only --api-key took effect,
                # which mismatched a non-deepseek key against api.deepseek.com and
                # 401'd). Map them through so the SUT endpoint/model/key agree.
                deepseek_model=args.model,
                deepseek_base_url=args.base_url,
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
    elif args.task == "gaia":
        from worldcalib.agentic.backends.gaia.optimizer import (
            GaiaOptimizer,
            GaiaOptimizerConfig,
        )

        gaia_levels = tuple(
            int(x) for x in str(args.gaia_levels).split(",") if x.strip()
        )
        optimizer = GaiaOptimizer(
            GaiaOptimizerConfig(
                **shared,
                gaia_levels=gaia_levels,
                gaia_runs=args.gaia_runs,
                gaia_concurrency=args.gaia_concurrency,
                gaia_train_size=args.gaia_train_size,
                gaia_test_size=args.gaia_test_size,
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
            harbor_max_turns=args.autolab_max_turns,
            harbor_max_task_seconds=int(args.autolab_max_task_minutes * 60),
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
    elif args.task == "tb2":
        from worldcalib.tb2.tb2_optimizer import Tb2Optimizer, Tb2OptimizerConfig

        # Every flag defaults to None so an omitted one falls through to
        # Tb2OptimizerConfig's default rather than silently re-pinning the SUT,
        # the repeats, or the MEAN aggregation to something else.
        tb2_kwargs = dict(
            **shared,
            task_ids=tuple(_csv(args.tb2_task_ids)),
            force=args.tb2_force,
        )
        for flag, key in (
            ("tb2_dataset", "tasks_path"),
            ("tb2_terminus2_source", "terminus2_source_path"),
            ("tb2_harbor_python", "harbor_python"),
            ("tb2_harbor_binary", "harbor_binary"),
            ("tb2_agent", "harbor_agent"),
            ("tb2_harbor_model", "harbor_model"),
            ("tb2_api_base", "api_base"),
            ("tb2_repeats", "harbor_n_attempts"),
            ("tb2_concurrency", "harbor_concurrency"),
            ("tb2_timeout_multiplier", "harbor_timeout_multiplier"),
            ("tb2_max_turns", "harbor_max_turns"),
            ("tb2_env_file", "harbor_env_file"),
            ("tb2_harbor_environment", "harbor_environment"),
        ):
            value = getattr(args, flag, None)
            if value is not None:
                tb2_kwargs[key] = value
        if args.tb2_max_task_minutes is not None:
            tb2_kwargs["harbor_max_task_seconds"] = int(args.tb2_max_task_minutes * 60)
        optimizer = Tb2Optimizer(Tb2OptimizerConfig(**tb2_kwargs))
    elif args.task == "spider2":
        from worldcalib.agentic.backends.spider2.optimizer import (
            Spider2Optimizer,
            Spider2OptimizerConfig,
        )

        optimizer = Spider2Optimizer(
            Spider2OptimizerConfig(
                **shared,
                spider2_runs=args.spider2_runs,
                spider2_concurrency=args.spider2_concurrency,
            )
        )
    elif args.task == "toolathlon":
        from worldcalib.agentic.backends.toolathlon.optimizer import (
            ToolathlonOptimizer,
            ToolathlonOptimizerConfig,
        )

        toolathlon_kwargs = dict(
            **shared,
            toolathlon_concurrency=args.toolathlon_concurrency,
            toolathlon_maxstep=args.toolathlon_maxstep,
            toolathlon_per_task_timeout_s=args.toolathlon_per_task_timeout_s,
            force=args.toolathlon_force,
        )
        if args.toolathlon_root is not None:
            toolathlon_kwargs["toolathlon_root"] = args.toolathlon_root
        optimizer = ToolathlonOptimizer(ToolathlonOptimizerConfig(**toolathlon_kwargs))
    elif args.task == "appworld":
        from worldcalib.agentic.backends.appworld.optimizer import (
            AppWorldOptimizer,
            AppWorldOptimizerConfig,
        )

        optimizer = AppWorldOptimizer(
            AppWorldOptimizerConfig(
                **shared,
                appworld_concurrency=args.appworld_concurrency,
                appworld_max_interactions=args.appworld_max_interactions,
                appworld_per_task_timeout_s=args.appworld_per_task_timeout_s,
                appworld_repeats=args.appworld_repeats,
                force=args.appworld_force,
            )
        )
    else:
        optimizer = LocomoOptimizer(LocomoOptimizerConfig(**shared))

    payload = optimizer.run()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
