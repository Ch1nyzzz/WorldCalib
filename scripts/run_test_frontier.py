"""Evaluate an existing WorldCalib run's train-frontier candidates on the
held-out test split.

Usage:
    python scripts/run_test_frontier.py \\
        --run-dir runs/longmemeval_s_..._wmc_iter30_... \\
        --task longmemeval --variant s

Mirrors what Optimizer1's `--test-frontier` flag does at the end of an
optimization run: pick the Pareto-quality frontier from existing candidates,
re-eval each on the test split, and write `test_frontier/` + `test_frontier_summary.json`
into the run directory.
"""

from __future__ import annotations

import argparse
import os
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
from worldcalib.scaffolds import DEFAULT_EVOLUTION_SEED_SCAFFOLDS


def _load_project_env() -> None:
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--task", choices=("locomo", "longmemeval"), required=True)
    p.add_argument("--variant", default="s", help="LongMemEval variant (s/m/oracle)")
    p.add_argument("--test-split", default="test")
    p.add_argument("--test-limit", type=int, default=0)
    p.add_argument("--candidate-limit", type=int, default=0)
    p.add_argument("--eval-workers", type=int, default=64)
    p.add_argument("--eval-timeout-s", type=int, default=300)
    p.add_argument("--model", default="deepseek-v4-flash")
    p.add_argument("--base-url", default="https://api.deepseek.com")
    p.add_argument("--api-key", default="EMPTY")
    p.add_argument(
        "--judge-model", default=DEFAULT_LONGMEMEVAL_JUDGE_MODEL
    )
    p.add_argument(
        "--judge-base-url", default=DEFAULT_LONGMEMEVAL_JUDGE_BASE_URL
    )
    p.add_argument("--judge-api-key", default=None)
    args = p.parse_args()

    _load_project_env()

    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        raise SystemExit(f"run dir does not exist: {run_dir}")

    shared = dict(
        run_id=run_dir.name,
        out_dir=run_dir,
        iterations=0,
        split="train",
        limit=0,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        eval_timeout_s=args.eval_timeout_s,
        max_eval_workers=args.eval_workers,
        scaffolds=tuple(
            DEFAULT_LONGMEMEVAL_SCAFFOLDS
            if args.task == "longmemeval"
            else DEFAULT_EVOLUTION_SEED_SCAFFOLDS
        ),
        scaffold_extra={},
        resume=True,
        skip_scaffold_eval=True,
        test_frontier=True,
        test_split=args.test_split,
        test_limit=args.test_limit,
        test_frontier_candidate_limit=args.candidate_limit,
    )

    if args.task == "longmemeval":
        optimizer = LongMemEvalOptimizer(
            LongMemEvalOptimizerConfig(
                **shared,
                dataset_variant=args.variant,
                judge_model=args.judge_model,
                judge_base_url=args.judge_base_url,
                judge_api_key=args.judge_api_key,
                use_llm_judge=True,
            )
        )
    else:
        optimizer = LocomoOptimizer(LocomoOptimizerConfig(**shared))

    candidates = optimizer._load_existing_candidates()
    if not candidates:
        raise SystemExit(f"no candidates loaded from {run_dir}/candidate_results/")
    print(f"loaded {len(candidates)} candidates from {run_dir}")

    summary = optimizer._run_test_frontier(candidates)
    print(f"\ntest_frontier complete:")
    print(f"  train_frontier_count: {summary['train_frontier_count']}")
    print(f"  evaluated_count: {summary['evaluated_count']}")
    print(f"  failed_count: {summary['failed_count']}")
    print(f"  summary: {summary['summary_path']}")
    print(f"  test_pareto_frontier: {summary['test_pareto_frontier_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
