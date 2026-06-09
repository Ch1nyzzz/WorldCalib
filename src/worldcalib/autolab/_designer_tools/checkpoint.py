#!/usr/bin/env python3
"""In-sandbox `worldcalib-checkpoint` client for AutoLab designer mode.

Records a design you consider worth keeping. The host EvalBridge freezes a copy
of the current terminus-2 source so later edits in the same session cannot
mutate what this checkpoint refers to; at session end the harness evaluates
every checkpoint on the held-out test split and picks a winner.

Usage (from the designer workspace root):
    python .worldcalib_tools/checkpoint.py --note "from-scratch ReAct loop, no retries"

Pure stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

CHECKPOINT_REQUEST_DIR = "checkpoint_requests"
CHECKPOINT_RESULT_DIR = "checkpoint_results"
EVAL_REQUEST_DIR = "eval_requests"  # workspace-root marker (created by the bridge)
DEFAULT_SOURCE_REL = "terminus2_agent"


def find_workspace_root(start: str) -> str:
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, EVAL_REQUEST_DIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def to_workspace_rel(source: str, workspace: str) -> str:
    p = (
        os.path.abspath(source)
        if os.path.isabs(source)
        else os.path.abspath(os.path.join(workspace, source))
    )
    return os.path.relpath(p, workspace).replace(os.sep, "/")


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a checkpoint design for held-out test.")
    ap.add_argument("--note", required=True, help="what this design is / why it should be kept")
    ap.add_argument(
        "--direction",
        default="",
        help="short tag for the DIRECTION/paradigm this design explores (e.g. "
        "'best-snapshot-ratchet', 'two-phase-plan-execute', 'reflexion-retry'). "
        "Used to enforce the >=3 completely-different-directions floor.",
    )
    ap.add_argument(
        "--mechanism",
        default="",
        help="one line: the mechanism-level idea (what is structurally different).",
    )
    ap.add_argument("--source", default=DEFAULT_SOURCE_REL, help="terminus-2 source root")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--poll", type=float, default=2.0)
    args = ap.parse_args()

    workspace = find_workspace_root(os.getcwd())
    source_rel = to_workspace_rel(args.source, workspace)

    ckpt_id = f"ckpt_{int(time.time() * 1000)}_{os.getpid()}"
    request = {
        "source_rel": source_rel,
        "note": args.note,
        "direction": args.direction,
        "mechanism": args.mechanism,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    req_dir = os.path.join(workspace, CHECKPOINT_REQUEST_DIR)
    res_path = os.path.join(workspace, CHECKPOINT_RESULT_DIR, f"{ckpt_id}.json")
    os.makedirs(req_dir, exist_ok=True)

    tmp = os.path.join(req_dir, f"{ckpt_id}.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(request, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(req_dir, f"{ckpt_id}.json"))

    print(f"[worldcalib-checkpoint] submitted {ckpt_id}; waiting for host ack...",
          file=sys.stderr, flush=True)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if os.path.isfile(res_path):
            break
        time.sleep(args.poll)
    else:
        print(f"[worldcalib-checkpoint] TIMEOUT waiting for {res_path}", file=sys.stderr)
        return 2

    with open(res_path, "r", encoding="utf-8") as fh:
        result = json.load(fh)

    if result.get("status") == "ok":
        print(
            f"STATUS: ok  checkpoint={result.get('ckpt_id')}  "
            f"total_checkpoints={result.get('n_checkpoints')}"
        )
        print("frozen at:", result.get("frozen_source_path"))
        print("note:", result.get("note"))
        return 0
    print(f"STATUS: {result.get('status')}")
    print("ERROR:", result.get("error", "(none)"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
