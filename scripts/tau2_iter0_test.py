"""tau2 iter0 check: seed frontier + WMC seed + no external critic.

Runs the Tau2Optimizer with iterations=0 (seed frontier only, no proposer) to
verify the optimizer wiring:
  - the pass-through seed scaffold is evaluated over real tau2 episodes
    (agent + deepseek user simulator + stateful environment)
  - candidate_results carry a per-task-type (reward_basis) score_breakdown
  - world_model_calibration.md is seeded (self-distill)
  - NO critic_feedback.md is produced (external critic disabled)

Run from .venv-tau2-eval with .env sourced (DEEPSEEK_API_KEY):
    set -a && source .env && set +a && \
        .venv-tau2-eval/bin/python scripts/tau2_iter0_test.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from loguru import logger

from worldcalib.agentic.backends.tau2.optimizer import (
    Tau2Optimizer,
    Tau2OptimizerConfig,
)

logger.remove()  # silence tau2's verbose per-call logging

RUN_DIR = Path("runs/tau2_iter0")


def main() -> None:
    config = Tau2OptimizerConfig(
        run_id="tau2_iter0",
        out_dir=RUN_DIR,
        iterations=0,
        split="train",
        limit=3,
        tau2_domain="telecom",
        tau2_train_size=3,
        tau2_test_size=3,
        tau2_max_steps=30,
        tau2_concurrency=3,
        proposer_variant="calib",
        dry_run_probe_k=0,
    )
    opt = Tau2Optimizer(config)
    opt.run()

    print("RUN OK")
    print(
        "world_model_calibration.md exists:",
        (RUN_DIR / "world_model_calibration.md").exists(),
    )
    print(
        "critic_feedback.md exists (must be False):",
        (RUN_DIR / "critic_feedback.md").exists(),
    )
    for path in sorted(glob.glob(str(RUN_DIR / "candidate_results" / "*.json"))):
        data = json.load(open(path))
        print(
            Path(path).name,
            "passrate=", data["candidate"]["passrate"],
            "avg=", data["candidate"]["average_score"],
            "score_breakdown=", data["score_breakdown"],
        )


if __name__ == "__main__":
    main()
