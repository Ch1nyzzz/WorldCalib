"""M1 smoke: run the seed pass-through agent scaffold over a DB train split.

Verifies the agent evaluation closed loop:
  build seed scaffold -> AgentEvaluationRunner -> real episodes -> per-category
  (by task-type) score_breakdown. Passrate should match bare-deepseek behavior,
  proving the scaffold wrapper is lossless.

Run:
  DSK=$(grep -m1 '^DEEPSEEK_API_KEY=' .env | cut -d= -f2- | tr -d '"'"' ")
  DEEPSEEK_API_KEY="$DSK" python scripts/agent_eval_smoke.py [task] [limit]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from worldcalib.agentic.backends.agentbench import build_agent_scaffold
from worldcalib.agentic.backends.agentbench.data import load_agentbench_examples
from worldcalib.agentic.backends.agentbench.evaluation import AgentEvaluationRunner
from worldcalib.scaffolds.base import ScaffoldConfig

CONTROLLER_URL = "http://localhost:5020/api"


def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else "db"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    concurrency = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("set DEEPSEEK_API_KEY")

    examples = load_agentbench_examples(
        task,
        "train",
        controller_url=CONTROLLER_URL,
        train_size=limit,
        test_size=limit,
        limit=limit,
    )
    print(f"loaded {len(examples)} {task} train episodes")

    out_dir = Path("runs/agent_smoke")
    runner = AgentEvaluationRunner(
        examples=examples,
        out_dir=out_dir,
        controller_url=CONTROLLER_URL,
        task=task,
        api_key=api_key,
        concurrency=concurrency,
    )
    scaffold = build_agent_scaffold("agent_passthrough")
    candidate = runner.evaluate_scaffold(
        scaffold=scaffold,
        scaffold_name="agent_passthrough",
        config=ScaffoldConfig(),
        candidate_id=f"smoke_seed_{task}",
    )

    print(f"\npassrate={candidate.passrate:.3f}  avg_score={candidate.average_score:.3f}  count={candidate.count}")
    payload = json.loads(
        (out_dir / "candidate_results" / f"smoke_seed_{task}.json").read_text()
    )
    print("per-category score_breakdown (by task-type):")
    print(json.dumps(payload["score_breakdown"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
