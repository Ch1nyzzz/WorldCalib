#!/usr/bin/env python3
"""In-sandbox `worldcalib-eval` client for AutoLab designer mode.

Runs INSIDE the proposer's docker sandbox (which has no harbor). It does not
evaluate anything itself: it drops an eval request into the workspace; the
host-side EvalBridge runs the (slow) harbor eval and writes the result back.

Evals are SLOW (each AutoLab task is ~15–60 min, run in parallel on the host),
so this client is ASYNC by design — it never blocks the agent for the full eval:

    # submit an eval (returns a req_id; waits only briefly for a fast result)
    python .worldcalib_tools/eval.py --subset smoke
    python .worldcalib_tools/eval.py --subset train --source terminus2_agent

    # if it printed STATUS: pending, do other design work, then collect later:
    python .worldcalib_tools/eval.py --collect <req_id>

Each call waits at most `--max-wait` seconds (default 480, safely under the bash
tool timeout). If the result is not ready it prints `STATUS: pending` plus the
exact `--collect` command to resume. Use the wait time productively: read code,
refine the next idea, update DESIGN_LOG.md — do not spin on --collect.

`--subset smoke` = a small cheap subset of the train tasks (fast, generous quota);
`--subset train` = the full train set (slow, small quota). Results report each
train task's score + pass/fail + flip vs the iter0 baseline, plus your budget.

Pure stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

EVAL_REQUEST_DIR = "eval_requests"
EVAL_RESULT_DIR = "eval_results"
DEFAULT_SOURCE_REL = "terminus2_agent"


def find_workspace_root(start: str) -> str:
    """Walk up from `start` to the dir that holds `eval_requests` (the bridge
    creates it at the workspace root). Fall back to `start`."""
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, EVAL_REQUEST_DIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def to_workspace_rel(source: str, workspace: str) -> str:
    """Normalize `--source` to a path relative to the workspace root."""
    p = (
        os.path.abspath(source)
        if os.path.isabs(source)
        else os.path.abspath(os.path.join(workspace, source))
    )
    return os.path.relpath(p, workspace).replace(os.sep, "/")


def _await_result(res_path: str, max_wait: float, poll: float) -> dict | None:
    """Poll for the result file for up to `max_wait` seconds. None if not ready."""
    deadline = time.time() + max_wait
    last_tick = 0.0
    started = time.time()
    while time.time() < deadline:
        if os.path.isfile(res_path):
            with open(res_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        now = time.time()
        if now - last_tick >= 30.0:
            print(
                f"[worldcalib-eval] waiting on host eval ({int(now - started)}s)...",
                file=sys.stderr,
                flush=True,
            )
            last_tick = now
        time.sleep(poll)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Request/collect a harbor eval from the host bridge.")
    ap.add_argument(
        "--tasks",
        default=None,
        help="CSV of train task ids to evaluate — YOUR free choice (e.g. "
        "--tasks levenshtein_distance,radix_sort). Overrides --subset.",
    )
    ap.add_argument("--subset", choices=["smoke", "train", "full"], default=None,
                    help="shortcut: 'smoke' = a small cheap subset, 'train'/'full' = all train tasks")
    ap.add_argument("--collect", metavar="REQ_ID", default=None,
                    help="resume waiting for a previously-submitted eval by its req_id")
    ap.add_argument(
        "--source",
        default=DEFAULT_SOURCE_REL,
        help="terminus-2 source root (parent of the terminus_2 package), relative or absolute.",
    )
    ap.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="harbor attempts per task (k). 1 = cheap probe; >=2 = noise-reduced "
        "confirm (use before checkpointing a design you believe in).",
    )
    ap.add_argument("--note", default="", help="optional free-text note recorded with the request")
    ap.add_argument(
        "--max-wait",
        type=float,
        default=float(os.environ.get("WORLDCALIB_EVAL_MAX_WAIT_S", "480") or 480),
        help=(
            "max seconds to wait this call before returning STATUS: pending. Defaults "
            "to $WORLDCALIB_EVAL_MAX_WAIT_S (set by the launcher just under the sandbox "
            "bash timeout so the call BLOCKS until the eval finishes), else 480. Pass a "
            "small value (e.g. --max-wait 1) to return immediately and --collect later."
        ),
    )
    ap.add_argument("--poll", type=float, default=3.0, help="poll interval seconds")
    args = ap.parse_args()

    submit = bool(args.tasks or args.subset)
    if submit == bool(args.collect):
        print(
            "error: pass exactly one of {--tasks / --subset} (to submit) or "
            "--collect <req_id> (to resume).",
            file=sys.stderr,
        )
        return 2

    workspace = find_workspace_root(os.getcwd())

    if submit:
        source_rel = to_workspace_rel(args.source, workspace)
        req_id = f"{int(time.time() * 1000)}_{os.getpid()}"
        request = {
            "source_rel": source_rel,
            "note": args.note,
            "n_attempts": max(1, int(args.attempts)),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if args.tasks:
            request["task_ids"] = [x.strip() for x in args.tasks.split(",") if x.strip()]
            scope = f"tasks={args.tasks}"
        else:
            request["subset"] = args.subset
            scope = f"subset={args.subset}"
        req_dir = os.path.join(workspace, EVAL_REQUEST_DIR)
        os.makedirs(req_dir, exist_ok=True)
        tmp = os.path.join(req_dir, f"{req_id}.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(request, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, os.path.join(req_dir, f"{req_id}.json"))
        print(
            f"[worldcalib-eval] submitted req={req_id} {scope} source={source_rel}",
            file=sys.stderr,
            flush=True,
        )
    else:
        req_id = args.collect

    res_path = os.path.join(workspace, EVAL_RESULT_DIR, f"{req_id}.json")
    result = _await_result(res_path, args.max_wait, args.poll)

    if result is None:
        print("STATUS: pending")
        print(f"req_id={req_id}")
        print(
            "The host eval is still running (these take ~15-60 min). Do other design "
            "work, then resume waiting with:"
        )
        print(f"  python .worldcalib_tools/eval.py --collect {req_id}")
        return 0  # not an error — the submission succeeded; result is just not ready

    _print_summary(result)
    return 0 if result.get("status") == "ok" else 1


def _print_summary(result: dict) -> None:
    status = result.get("status")
    if status in ("budget_exhausted", "budget_insufficient"):
        print(f"STATUS: {status}")
        print(result.get("message", ""))
        print("BUDGET:", json.dumps(result.get("budget", {})))
        return
    if status != "ok":
        print(f"STATUS: {status}")
        print("ERROR:", result.get("error", "(none)"))
        if result.get("available_tasks"):
            print("AVAILABLE TASKS:", ", ".join(result["available_tasks"]))
        print("BUDGET:", json.dumps(result.get("budget", {})))
        return

    print(f"STATUS: ok  scope={result.get('scope')}  req={result.get('req_id')}")
    print(
        f"passrate={result.get('passrate')}  avg_score={result.get('avg_score')}  "
        f"net_flips={result.get('net_flips')} "
        f"(+{result.get('n_fail_to_pass')} / -{result.get('n_pass_to_fail')})  "
        f"n_tasks={result.get('n_tasks')}  took={result.get('duration_s')}s"
    )
    print("BUDGET:", json.dumps(result.get("budget", {})))
    print("\nPER-TASK (task_id | score | pass | baseline | flip | flags):")
    for t in result.get("per_task", []):
        flags = []
        if t.get("timed_out"):
            flags.append("timed_out")
        if t.get("errored"):
            flags.append("errored")
        print(
            f"  {t['task_id']:<32} {t['score']:>6}  "
            f"{'PASS' if t['passed'] else 'fail':<4}  "
            f"base={'PASS' if t.get('baseline_passed') else 'fail'}  "
            f"{t.get('flip') or '-':<10} {','.join(flags)}"
        )
    if result.get("traces_dir"):
        print(
            f"\nPER-TASK TRACES (the agent's own trajectory — READ THESE to diagnose "
            f"why a task failed): {result['traces_dir']}/<task_id>.log"
        )
    print("Full result JSON saved at:", result.get("result_path", "(n/a)"))


if __name__ == "__main__":
    raise SystemExit(main())
