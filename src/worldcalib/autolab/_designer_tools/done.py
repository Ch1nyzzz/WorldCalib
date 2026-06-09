#!/usr/bin/env python3
"""In-sandbox `worldcalib-done` — declare that you believe you've converged.

Call this ONLY when you genuinely think there is no more meaningful optimization
to find. It records your convergence judgement; the harness then checks the hard
floor (you must have implemented + evaluated + checkpointed >=N *completely
different* directions). If the floor is met, your judgement is honored and the
session ends. If not, you'll be asked to explore another genuinely different
direction before you may stop.

Usage (from the workspace root):
    python .worldcalib_tools/done.py --reason "tried ratchet / two-phase / reflexion; all plateau at ~X; remaining gap looks model-limited"

Pure stdlib.
"""

from __future__ import annotations

import argparse
import os
import time

EVAL_REQUEST_DIR = "eval_requests"  # workspace-root marker (created by the bridge)
CONVERGED_FILE = "CONVERGED.md"


def find_workspace_root(start: str) -> str:
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, EVAL_REQUEST_DIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Declare convergence (subject to the directions floor).")
    ap.add_argument(
        "--reason",
        required=True,
        help="why you believe no more optimization is worthwhile (cite the directions "
        "you tried and what the evidence shows).",
    )
    args = ap.parse_args()

    workspace = find_workspace_root(os.getcwd())
    path = os.path.join(workspace, CONVERGED_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# CONVERGED ({time.strftime('%Y-%m-%dT%H:%M:%S')})\n\n")
        fh.write(args.reason.strip() + "\n")

    print(f"Recorded convergence claim at {CONVERGED_FILE}.")
    print(
        "The harness will honor it ONLY if the >=N-completely-different-directions "
        "floor is met; otherwise you'll be asked to explore another direction."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
