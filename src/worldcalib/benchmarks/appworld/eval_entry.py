"""AppWorld eval engine — worldcalib-free, runs in the isolated ``.venv-appworld``.

Evaluates a candidate's editable agent (``agent.py``) over a list of AppWorld
task ids with PROCESS parallelism (AppWorld holds module-level/db state, so each
task gets its own process), grades each with ``world.evaluate().success``
(AppWorld task-goal completion), writes per-task raw dumps for the proposer's
evidence, and a roll-up results.json + summary.json.

This is the eval core the optimizer's external runner spawns as a subprocess; it
is also runnable standalone for a seed/iter-0 score. It is import-light on
purpose (stdlib + appworld + openai only) and loads the candidate ``agent.py`` by
FILE PATH so it never imports the worldcalib package (pydantic-v2 conflict).

Usage (from an environment with AppWorld installed):
    APPWORLD_ROOT=/path/to/appworld-data python -m worldcalib.benchmarks.appworld.eval_entry \
        --agent-path <candidate>/agent.py \
        --task-ids id1,id2,...  (or --split train --limit 50) \
        --out <dump_dir> --concurrency 64 --max-interactions 50
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any


def _load_agent_module(agent_path: str):
    """Import an agent.py by path so the worker never imports the worldcalib package."""
    path = Path(agent_path)
    spec = importlib.util.spec_from_file_location("appworld_candidate_agent", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dump_transcript(transcript: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for m in transcript or []:
        role = m.get("role", "?")
        out.append(f"===== {role} =====\n{m.get('content','')}")
    return "\n\n".join(out)


def run_one_task(
    task_id: str,
    *,
    agent_path: str,
    out_dir: str,
    experiment_name: str,
    max_interactions: int,
) -> dict[str, Any]:
    """Worker: build the AppWorld env, run the candidate agent, grade, dump. Never raises."""
    started = time.time()
    task_out = Path(out_dir) / task_id
    task_out.mkdir(parents=True, exist_ok=True)
    try:
        from appworld import AppWorld  # imported inside the worker (appworld venv)

        agent = _load_agent_module(agent_path)
        world = AppWorld(
            task_id=task_id,
            experiment_name=experiment_name,
            max_interactions=max_interactions,
        )
        try:
            telemetry = agent.solve(world)
            tracker = world.evaluate(suppress_errors=True)
            success = bool(getattr(tracker, "success", False))
            pass_count = int(getattr(tracker, "pass_count", 0) or 0)
            total_count = int(getattr(tracker, "total_count", 0) or 0)
            report = ""
            try:
                report = str(tracker.report())[:4000]
            except Exception:  # noqa: BLE001
                pass
        finally:
            try:
                world.close()
            except Exception:  # noqa: BLE001
                pass

        row = {
            "task_id": task_id,
            "success": success,
            "score": 1.0 if success else 0.0,
            "pass_count": pass_count,
            "total_count": total_count,
            "steps": telemetry.get("steps"),
            "prompt_tokens": telemetry.get("prompt_tokens", 0),
            "completion_tokens": telemetry.get("completion_tokens", 0),
            "agent_error": telemetry.get("error"),
            "error": None,
            "seconds": round(time.time() - started, 1),
        }
        # Raw evidence for the proposer: per-task outcome + full ReAct transcript.
        (task_out / "result.json").write_text(
            json.dumps({**row, "eval_report": report}, indent=2, ensure_ascii=False)
        )
        (task_out / "transcript.txt").write_text(_dump_transcript(telemetry.get("transcript") or []))
        return row
    except Exception as e:  # noqa: BLE001 — one bad task must not kill the batch
        row = {
            "task_id": task_id,
            "success": False,
            "score": 0.0,
            "error": f"{type(e).__name__}: {e}",
            "seconds": round(time.time() - started, 1),
        }
        try:
            (task_out / "result.json").write_text(json.dumps(row, indent=2, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
        return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-path", required=True, help="candidate agent.py")
    ap.add_argument("--split", default="train")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--task-ids", default="", help="comma-separated explicit ids (overrides split)")
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--max-interactions", type=int, default=50)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--experiment-name", default="",
        help="AppWorld experiment_name (default derived from --out; set explicitly "
             "to keep concurrent candidates/reps from sharing output dirs)",
    )
    args = ap.parse_args()

    from appworld import load_task_ids

    if args.task_ids.strip():
        ids = [t.strip() for t in args.task_ids.split(",") if t.strip()]
    else:
        ids = load_task_ids(args.split)
        if args.limit:
            ids = ids[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    agent_path = args.agent_path
    experiment_name = args.experiment_name.strip() or f"appworld_eval_{out_dir.name}"

    print(f"AppWorld eval: n={len(ids)} concurrency={args.concurrency} agent={agent_path}", flush=True)
    print(f"  APPWORLD_ROOT={os.environ.get('APPWORLD_ROOT')}  out={out_dir}", flush=True)
    t0 = time.time()

    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(
                run_one_task,
                tid,
                agent_path=agent_path,
                out_dir=str(out_dir),
                experiment_name=experiment_name,
                max_interactions=args.max_interactions,
            ): tid
            for tid in ids
        }
        done = 0
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            done += 1
            mark = "OK" if res.get("success") else ("ER" if res.get("error") else "..")
            print(f"  [{done}/{len(ids)}] {mark} {res['task_id']} "
                  f"(steps={res.get('steps')}, {res.get('seconds')}s)"
                  + (f" ERR {res['error']}" if res.get("error") else ""), flush=True)

    n = len(results)
    n_pass = sum(1 for r in results if r.get("success"))
    summary = {
        "split": args.split,
        "n_tasks": n,
        "n_pass": n_pass,
        "n_error": sum(1 for r in results if r.get("error")),
        "passrate": (n_pass / n if n else 0.0),
        "concurrency": args.concurrency,
        "max_interactions": args.max_interactions,
        "wall_seconds": round(time.time() - t0, 1),
        "agent_path": agent_path,
        "model": os.environ.get("APPWORLD_MODEL") or os.environ.get("MODEL_NAME") or "deepseek-v4-flash",
    }
    (out_dir / "results.json").write_text(json.dumps({"summary": summary, "tasks": results}, indent=2))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
