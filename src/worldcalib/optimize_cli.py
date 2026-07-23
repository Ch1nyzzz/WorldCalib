"""Command-line entry point for the benchmark scope reported in the paper."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Any

from worldcalib.paths import runtime_root
from worldcalib.world_model import EMPTY_WORLD_MODEL


BENCHMARKS = (
    "longmemeval",
    "locomo",
    "gaia",
    "appworld",
    "tb2",
    "toolathlon",
    "spider2",
)

_PAPER_PROPOSER_MODEL = {
    "longmemeval": "kimi-k2.6",
    "locomo": "kimi-k2.6",
    "gaia": "kimi-k2.7",
    "appworld": "kimi-k2.7",
    "tb2": "gpt-5.6-sol",
    "spider2": "kimi-k2.7",
    "toolathlon": "kimi-k2.7",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldcalib-optimize",
        description=(
            "Run WorldCalib on a paper-scoped benchmark. WebShop, OS, and other "
            "internal experiments are intentionally unsupported."
        ),
    )
    parser.add_argument("benchmark", choices=BENCHMARKS)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)

    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--split", choices=("train", "test"), default="train")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--eval-timeout-s", type=int, default=300)
    parser.add_argument("--eval-workers", type=int, default=1)
    parser.add_argument("--max-context-chars", type=int, default=6000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-scaffold-eval", action="store_true")
    parser.add_argument("--baseline-dir", type=Path, default=None)
    parser.add_argument("--selection-policy", choices=("self", "default"), default="self")
    parser.add_argument("--no-summary", action="store_true")
    parser.add_argument("--test-frontier", action="store_true")
    parser.add_argument("--test-limit", type=int, default=0)
    parser.add_argument("--test-frontier-candidate-limit", type=int, default=0)
    parser.add_argument("--trace-baseline-path", type=Path, default=None)

    parser.add_argument("--proposer-variant", choices=("calib", "nowmc"), default="calib")
    parser.add_argument("--prev-calibration", type=Path, default=None)
    parser.add_argument("--proposer-agent", choices=("claude", "codex"), default=None)
    parser.add_argument("--proposer-model", default=None)
    parser.add_argument("--proposer-effort", default=None)
    parser.add_argument("--proposer-base-url", default=None)
    parser.add_argument("--proposer-auth-token", default=None)
    parser.add_argument("--claude-native-auth", action="store_true")
    parser.add_argument("--codex-home", default="")
    parser.add_argument("--propose-timeout-s", type=int, default=2400)
    parser.add_argument("--proposer-sandbox", choices=("none", "docker"), default="none")
    parser.add_argument("--proposer-docker-image", default="")
    parser.add_argument("--proposer-docker-user", default="")
    parser.add_argument("--proposer-docker-home", default="")
    parser.add_argument("--proposer-docker-env", action="append", default=[])
    parser.add_argument("--proposer-docker-mount", action="append", default=[])

    # Memory benchmarks.
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--split-path", type=Path, default=None)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--no-llm-judge", action="store_true")
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--judge-base-url", default=None)
    parser.add_argument("--judge-api-key", default=None)

    # GAIA and Spider2.
    parser.add_argument("--agent-runs", type=int, default=1)
    parser.add_argument("--agent-concurrency", type=int, default=8)
    parser.add_argument("--spider2-root", type=Path, default=None)

    # AppWorld.
    parser.add_argument("--appworld-root", type=Path, default=None)
    parser.add_argument("--appworld-python", type=Path, default=None)
    parser.add_argument("--appworld-concurrency", type=int, default=64)
    parser.add_argument("--appworld-repeats", type=int, default=1)
    parser.add_argument("--appworld-max-interactions", type=int, default=100)

    # Terminal-Bench 2.0.
    parser.add_argument("--tb2-tasks-path", type=Path, default=None)
    parser.add_argument("--tb2-terminus2-source", type=Path, default=None)
    parser.add_argument("--harbor-binary", type=Path, default=Path("harbor"))
    parser.add_argument("--tb2-model", default=None)
    parser.add_argument("--tb2-api-base", default=None)
    parser.add_argument("--tb2-repeats", type=int, default=2)
    parser.add_argument("--tb2-concurrency", type=int, default=8)
    parser.add_argument("--tb2-max-storage-mb", type=int, default=20_000)
    parser.add_argument("--tb2-env-file", type=Path, default=None)
    parser.add_argument("--tb2-environment", default=None)

    # Toolathlon.
    parser.add_argument("--toolathlon-root", type=Path, default=None)
    parser.add_argument("--toolathlon-concurrency", type=int, default=8)
    parser.add_argument("--toolathlon-maxstep", type=int, default=50)
    parser.add_argument("--force", action="store_true")
    return parser


def _load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _absolute(path: Path | None, work_dir: Path) -> Path | None:
    if path is None:
        return None
    expanded = path.expanduser()
    return (expanded if expanded.is_absolute() else work_dir / expanded).resolve()


def _common_config(args: argparse.Namespace, work_dir: Path, out_dir: Path) -> dict[str, Any]:
    benchmark = str(args.benchmark)
    proposer_agent = args.proposer_agent or ("codex" if benchmark == "tb2" else "claude")
    proposer_model = args.proposer_model or _PAPER_PROPOSER_MODEL.get(benchmark)
    proposer_effort = args.proposer_effort or "max"
    config: dict[str, Any] = {
        "run_id": args.run_id,
        "out_dir": out_dir,
        "work_dir": work_dir,
        "iterations": max(0, args.iterations),
        "split": args.split,
        "limit": max(0, args.limit),
        "model": args.model or os.environ.get("WORLDCALIB_MODEL", "deepseek-v4-flash"),
        "base_url": args.base_url or os.environ.get(
            "WORLDCALIB_BASE_URL", "https://api.deepseek.com/v1"
        ),
        "api_key": args.api_key or os.environ.get("DEEPSEEK_API_KEY", "EMPTY"),
        "eval_timeout_s": args.eval_timeout_s,
        "max_eval_workers": max(1, args.eval_workers),
        "max_context_chars": args.max_context_chars,
        "dry_run": args.dry_run,
        "resume": args.resume,
        "skip_scaffold_eval": args.skip_scaffold_eval,
        "baseline_dir": _absolute(args.baseline_dir, work_dir),
        "selection_policy": args.selection_policy,
        "summaries_in_workspace": not args.no_summary,
        "test_frontier": args.test_frontier,
        "test_limit": max(0, args.test_limit),
        "test_frontier_candidate_limit": max(0, args.test_frontier_candidate_limit),
        "trace_baseline_path": _absolute(args.trace_baseline_path, work_dir),
        "proposer_variant": args.proposer_variant,
        "proposer_agent": proposer_agent,
        "propose_timeout_s": args.propose_timeout_s,
        "proposer_sandbox": args.proposer_sandbox,
        "proposer_docker_image": args.proposer_docker_image,
        "proposer_docker_user": args.proposer_docker_user,
        "proposer_docker_home": args.proposer_docker_home,
        "proposer_docker_env": tuple(args.proposer_docker_env),
        "proposer_docker_mount": tuple(args.proposer_docker_mount),
        "claude_native_auth": args.claude_native_auth,
        "codex_home": args.codex_home,
        "data_path": _absolute(args.data_path, work_dir),
        "split_path": _absolute(args.split_path, work_dir),
        "allow_download": args.allow_download,
    }
    if proposer_agent == "codex":
        config["codex_model"] = proposer_model or "gpt-5.6-sol"
        config["codex_reasoning_effort"] = proposer_effort
    else:
        if proposer_model:
            config["claude_model"] = proposer_model
        config["claude_effort"] = proposer_effort
        if args.proposer_base_url:
            config["claude_base_url"] = args.proposer_base_url
        if args.proposer_auth_token:
            config["claude_auth_token"] = args.proposer_auth_token
    return config


def _build_optimizer(args: argparse.Namespace, common: dict[str, Any]):
    benchmark = str(args.benchmark)
    work_dir = Path(common["work_dir"])
    if benchmark == "locomo":
        from worldcalib.benchmarks.memory.locomo_optimizer import (
            LocomoOptimizer,
            LocomoOptimizerConfig,
        )

        memory = dict(common)
        memory["data_path"] = memory["data_path"] or work_dir / "data" / "locomo" / "locomo10.json"
        memory["split_path"] = memory["split_path"] or work_dir / "data" / "locomo" / "splits.json"
        return LocomoOptimizer(LocomoOptimizerConfig(**memory))
    if benchmark == "longmemeval":
        from worldcalib.benchmarks.memory.longmemeval import (
            DEFAULT_LONGMEMEVAL_JUDGE_BASE_URL,
            DEFAULT_LONGMEMEVAL_JUDGE_MODEL,
        )
        from worldcalib.benchmarks.memory.longmemeval_optimizer import (
            LongMemEvalOptimizer,
            LongMemEvalOptimizerConfig,
        )

        memory = dict(common)
        memory["data_path"] = memory["data_path"] or work_dir / "data" / "longmemeval" / "longmemeval_s_cleaned.json"
        memory["split_path"] = memory["split_path"] or work_dir / "data" / "longmemeval" / "splits_s.json"
        return LongMemEvalOptimizer(
            LongMemEvalOptimizerConfig(
                **memory,
                dataset_variant="s",
                judge_model=args.judge_model or DEFAULT_LONGMEMEVAL_JUDGE_MODEL,
                judge_base_url=args.judge_base_url or DEFAULT_LONGMEMEVAL_JUDGE_BASE_URL,
                judge_api_key=args.judge_api_key,
                use_llm_judge=not args.no_llm_judge,
            )
        )
    if benchmark == "gaia":
        from worldcalib.benchmarks.gaia.optimizer import GaiaOptimizer, GaiaOptimizerConfig

        return GaiaOptimizer(
            GaiaOptimizerConfig(
                **common,
                gaia_runs=max(1, args.agent_runs),
                gaia_concurrency=max(1, args.agent_concurrency),
                gaia_train_size=40,
                gaia_test_size=99,
            )
        )
    if benchmark == "spider2":
        from worldcalib.benchmarks.spider2.optimizer import (
            Spider2Optimizer,
            Spider2OptimizerConfig,
        )

        return Spider2Optimizer(
            Spider2OptimizerConfig(
                **common,
                spider2_root=_absolute(args.spider2_root, work_dir),
                spider2_runs=max(1, args.agent_runs),
                spider2_concurrency=max(1, args.agent_concurrency),
            )
        )
    if benchmark == "appworld":
        from worldcalib.benchmarks.appworld.optimizer import (
            AppWorldOptimizer,
            AppWorldOptimizerConfig,
        )

        return AppWorldOptimizer(
            AppWorldOptimizerConfig(
                **common,
                appworld_root=_absolute(args.appworld_root, work_dir),
                appworld_python=_absolute(args.appworld_python, work_dir),
                appworld_concurrency=max(1, args.appworld_concurrency),
                appworld_repeats=max(1, args.appworld_repeats),
                appworld_max_interactions=max(1, args.appworld_max_interactions),
                force=args.force,
            )
        )
    if benchmark == "tb2":
        from worldcalib.benchmarks.tb2.tb2 import DEFAULT_TB2_API_BASE, DEFAULT_TB2_MODEL
        from worldcalib.benchmarks.tb2.tb2_optimizer import Tb2Optimizer, Tb2OptimizerConfig

        return Tb2Optimizer(
            Tb2OptimizerConfig(
                **common,
                tasks_path=_absolute(args.tb2_tasks_path, work_dir),
                terminus2_source_path=_absolute(args.tb2_terminus2_source, work_dir),
                harbor_binary=args.harbor_binary,
                harbor_model=args.tb2_model or DEFAULT_TB2_MODEL,
                api_base=args.tb2_api_base if args.tb2_api_base is not None else DEFAULT_TB2_API_BASE,
                harbor_n_attempts=max(1, args.tb2_repeats),
                harbor_concurrency=max(1, args.tb2_concurrency),
                max_storage_mb=args.tb2_max_storage_mb,
                harbor_env_file=_absolute(args.tb2_env_file, work_dir),
                harbor_environment=args.tb2_environment,
                force=args.force,
            )
        )
    if benchmark == "toolathlon":
        from worldcalib.benchmarks.toolathlon.optimizer import (
            ToolathlonOptimizer,
            ToolathlonOptimizerConfig,
        )

        return ToolathlonOptimizer(
            ToolathlonOptimizerConfig(
                **common,
                toolathlon_root=_absolute(args.toolathlon_root, work_dir),
                toolathlon_concurrency=max(1, args.toolathlon_concurrency),
                toolathlon_maxstep=max(1, args.toolathlon_maxstep),
                force=args.force,
            )
        )
    raise AssertionError(f"unhandled benchmark: {benchmark}")


def _seed_calibration(
    out_dir: Path, *, variant: str, previous: Path | None, work_dir: Path
) -> None:
    if variant == "nowmc":
        return
    target = out_dir / "world_model_calibration.md"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    source = _absolute(previous, work_dir)
    if source is not None:
        if not source.is_file():
            raise FileNotFoundError(f"previous calibration does not exist: {source}")
        shutil.copy2(source, target)
    else:
        target.write_text(EMPTY_WORLD_MODEL, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    work_dir = runtime_root(args.work_dir)
    os.environ["WORLDCALIB_WORKDIR"] = str(work_dir)
    env_file = _absolute(args.env_file, work_dir) or (work_dir / ".env")
    _load_env(env_file)
    out_dir = _absolute(args.out, work_dir) or (work_dir / "runs" / args.run_id)
    common = _common_config(args, work_dir, out_dir)
    _seed_calibration(
        out_dir,
        variant=args.proposer_variant,
        previous=args.prev_calibration,
        work_dir=work_dir,
    )
    optimizer = _build_optimizer(args, common)
    optimizer.run()
    print(f"WorldCalib run complete: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BENCHMARKS", "build_parser", "main"]
