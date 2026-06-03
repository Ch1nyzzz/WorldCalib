"""M2 iter0 check: seed frontier + WMC seed + no external critic.

Runs the AgentBenchOptimizer with iterations=0 (seed frontier only, no
proposer) to verify the optimizer wiring:
  - the pass-through seed scaffold is evaluated over real DB episodes
  - candidate_results carry a per-task-type score_breakdown
  - world_model_calibration.md is seeded (self-distill)
  - NO critic_feedback.md is produced (external critic disabled)
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from worldcalib.agentic.backends.agentbench.optimizer import (
    AgentBenchOptimizer,
    AgentBenchOptimizerConfig,
)

RUN_DIR = Path("runs/agent_m2_iter0")


def main() -> None:
    config = AgentBenchOptimizerConfig(
        run_id="agent_m2_iter0",
        out_dir=RUN_DIR,
        iterations=0,
        split="train",
        agentbench_task="db",
        agentbench_train_size=6,
        agentbench_concurrency=4,
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        proposer_variant="calib",
        dry_run_probe_k=0,
    )
    opt = AgentBenchOptimizer(config)
    opt.run()

    print("RUN OK")
    print("world_model_calibration.md exists:", (RUN_DIR / "world_model_calibration.md").exists())
    print("critic_feedback.md exists (must be False):", (RUN_DIR / "critic_feedback.md").exists())
    for path in sorted(glob.glob(str(RUN_DIR / "candidate_results" / "*.json"))):
        data = json.load(open(path))
        print(
            Path(path).name,
            "passrate=", data["candidate"]["passrate"],
            "score_breakdown=", list(data["score_breakdown"].keys()),
        )


if __name__ == "__main__":
    main()
