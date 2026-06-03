"""ARC-AGI-2 iter0 check: seed frontier + WMC seed + no external critic.

Runs the ArcOptimizer with iterations=0 (seed frontier only, no proposer) to
verify the optimizer wiring:
  - the pass-through seed scaffold is evaluated over real ARC-AGI-2 tasks
    (single-shot solve via the served target model, scored by exact grid
    match, pass@2)
  - candidate_results carry a per-task-type (grid-size-change) score_breakdown
  - world_model_calibration.md is seeded (self-distill)
  - NO critic_feedback.md is produced (external critic disabled)

The solver hits the served target model via worldcalib.model.LocalModelClient,
so point --model / --base-url (or the env defaults below) at a live endpoint
before running:
    set -a && source .env && set +a && \
        python scripts/arc_iter0_test.py
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from loguru import logger

from worldcalib.reasoning.arc_optimizer import (
    ArcOptimizer,
    ArcOptimizerConfig,
)

logger.remove()  # silence verbose per-call logging

RUN_DIR = Path("runs/arc_iter0")


def main() -> None:
    config = ArcOptimizerConfig(
        run_id="arc_iter0",
        out_dir=RUN_DIR,
        iterations=0,
        split="train",
        limit=4,
        model=os.environ.get("TARGET_MODEL", "deepseek-v4-flash"),
        base_url=os.environ.get("TARGET_BASE_URL", "https://api.deepseek.com"),
        api_key=os.environ.get("TARGET_API_KEY", "EMPTY"),
        arc_train_size=4,
        arc_test_size=4,
        arc_max_tokens=2048,
        arc_max_attempts=2,
        arc_concurrency=4,
        proposer_variant="calib",
        dry_run_probe_k=0,
    )
    opt = ArcOptimizer(config)
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
