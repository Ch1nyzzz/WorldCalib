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

from worldcalib.locomo_optimizer import LocomoOptimizer, LocomoOptimizerConfig
from worldcalib.longmemeval import (
    DEFAULT_LONGMEMEVAL_JUDGE_BASE_URL,
    DEFAULT_LONGMEMEVAL_JUDGE_MODEL,
    DEFAULT_LONGMEMEVAL_SCAFFOLDS,
)
from worldcalib.longmemeval_optimizer import (
    LongMemEvalOptimizer,
    LongMemEvalOptimizerConfig,
)
from worldcalib.model import DEFAULT_BASE_URL, DEFAULT_MODEL
from worldcalib.scaffolds import DEFAULT_EVOLUTION_SEED_SCAFFOLDS


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
        help="Optimizer1 selection policy (default, progressive, bandit, ...)",
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
        choices=("prose", "critic"),
        default="prose",
        help=(
            "Proposer world-model variant. 'prose' = append-only "
            "world_model_calibration.md protocol (default). 'critic' = ledger + "
            "adversarial reference-class critic subagent, no prose calibration file "
            "(routes to the <benchmark>_critic skill)."
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

    # The critic variant has no prose calibration file to seed.
    if args.proposer_variant != "critic":
        _seed_calibration(out_dir, args.prev_calibration)

    scaffolds_csv = (
        _csv(args.scaffolds)
        if args.scaffolds
        else list(
            DEFAULT_LONGMEMEVAL_SCAFFOLDS
            if args.task == "longmemeval"
            else DEFAULT_EVOLUTION_SEED_SCAFFOLDS
        )
    )
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
        critic_gate_enforce=args.critic_gate_enforce,
        dry_run_probe_k=args.dry_run_probe_k,
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
    else:
        optimizer = LocomoOptimizer(LocomoOptimizerConfig(**shared))

    payload = optimizer.run()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
