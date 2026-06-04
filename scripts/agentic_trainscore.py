"""Baseline (seed pass-through) score on an agentic task's TRAIN split.

Runs iter0 seed-frontier only (no proposer) over the full train split and prints
the pass-through scaffold's passrate / average reward / per-bucket score_breakdown
and a failure-status tally — i.e. "what does the un-optimized base agent score on
train". One task per invocation; run agentbench tasks from .venv-agentrl-eval and
tau2 from .venv-tau2-eval.

    set -a && source .env && set +a
    PYTHONPATH=src .venv-agentrl-eval/bin/python scripts/agentic_trainscore.py os
    PYTHONPATH=src .venv-agentrl-eval/bin/python scripts/agentic_trainscore.py webshop
    PYTHONPATH=src .venv-tau2-eval/bin/python   scripts/agentic_trainscore.py tau2
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

TRAIN_SIZE = 30


def _run_agentbench(task: str, run_dir: Path) -> None:
    from worldcalib.agentic.backends.agentbench.optimizer import (
        AgentBenchOptimizer,
        AgentBenchOptimizerConfig,
    )

    config = AgentBenchOptimizerConfig(
        run_id=run_dir.name,
        out_dir=run_dir,
        iterations=0,
        split="train",
        agentbench_task=task,
        agentbench_train_size=TRAIN_SIZE,
        agentbench_concurrency=8,
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        proposer_variant="calib",
    )
    AgentBenchOptimizer(config).run()


def _run_tau2(run_dir: Path, domain: str = "telecom") -> None:
    from loguru import logger

    logger.remove()  # silence tau2's per-call logging
    from worldcalib.agentic.backends.tau2.optimizer import (
        Tau2Optimizer,
        Tau2OptimizerConfig,
    )

    config = Tau2OptimizerConfig(
        run_id=run_dir.name,
        out_dir=run_dir,
        iterations=0,
        split="train",
        tau2_domain=domain,
        tau2_train_size=TRAIN_SIZE,
        tau2_concurrency=int(os.environ.get("TAU2_CONCURRENCY", "30")),
        proposer_variant="calib",
    )
    Tau2Optimizer(config).run()


def _summarize(run_dir: Path, task: str) -> None:
    print(f"\n===== {task} TRAIN baseline (seed pass-through) =====")
    for path in sorted(glob.glob(str(run_dir / "candidate_results" / "*.json"))):
        data = json.load(open(path))
        cand = data["candidate"]
        tasks = data.get("tasks", [])
        statuses = Counter(t.get("metadata", {}).get("status", "?") for t in tasks)
        print(f"candidate: {Path(path).name}")
        print(f"  episodes:     {cand['count']}")
        print(f"  passrate:     {cand['passrate']:.3f}")
        print(f"  avg reward:   {cand['average_score']:.3f}")
        print(f"  status tally: {dict(statuses)}")
        print("  score_breakdown (per bucket):")
        for bucket, info in data.get("score_breakdown", {}).items():
            print(f"    {bucket}: {info}")


def main() -> None:
    task = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if not task:
        sys.exit("usage: agentic_trainscore.py <os|webshop|db|alfworld|tau2>")
    # tau2 takes an optional domain as 2nd arg: `tau2 banking_knowledge`
    if task == "tau2" or task.startswith("tau2:"):
        domain = task.split(":", 1)[1] if ":" in task else (
            sys.argv[2] if len(sys.argv) > 2 else "telecom"
        )
        run_dir = Path(f"runs/trainscore_tau2_{domain}")
        _run_tau2(run_dir, domain)
        _summarize(run_dir, f"tau2/{domain}")
        print("RUN OK")
        return
    run_dir = Path(f"runs/trainscore_{task}")
    if False:
        pass
    else:
        _run_agentbench(task, run_dir)
    _summarize(run_dir, task)
    print("RUN OK")


if __name__ == "__main__":
    main()
