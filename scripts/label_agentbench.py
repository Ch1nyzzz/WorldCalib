"""Label EVERY registered episode of an agentbench task with the seed scaffold.

Runs the pass-through seed over the task's full index set (split='all') and dumps
{index: {passed, status, score}} to runs/<task>_label/labels.json — the pool used
to curate a frozen train/test split with a target baseline passrate.

    set -a && source .env && set +a
    PYTHONPATH=src .venv-agentrl-eval/bin/python scripts/label_agentbench.py os
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

from worldcalib.agentic.backends.agentbench.optimizer import (
    AgentBenchOptimizer,
    AgentBenchOptimizerConfig,
)


def main() -> None:
    task = (sys.argv[1] if len(sys.argv) > 1 else "os").strip().lower()
    run_dir = Path(f"runs/{task}_label")
    config = AgentBenchOptimizerConfig(
        run_id=run_dir.name,
        out_dir=run_dir,
        iterations=0,
        split="all",
        agentbench_task=task,
        agentbench_train_size=10_000,
        agentbench_test_size=10_000,
        agentbench_concurrency=8,
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        proposer_variant="calib",
    )
    AgentBenchOptimizer(config).run()

    labels: dict[int, dict] = {}
    for path in glob.glob(str(run_dir / "candidate_results" / "*.json")):
        for t in json.load(open(path)).get("tasks", []):
            idx = int(t["metadata"]["index"])
            labels[idx] = {
                "passed": bool(t["passed"]),
                "status": t["metadata"].get("status"),
                "score": t["score"],
            }
    out = run_dir / "labels.json"
    out.write_text(json.dumps(dict(sorted(labels.items())), indent=2))
    n = len(labels)
    npass = sum(1 for v in labels.values() if v["passed"])
    print(f"{task}: labeled {n} episodes, passed {npass} ({npass / n:.3f}) -> {out}")


if __name__ == "__main__":
    main()
