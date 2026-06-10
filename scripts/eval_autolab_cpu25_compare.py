#!/usr/bin/env python3
"""Evaluate one AutoLab terminus-2 source candidate on the full CPU-only task set.

This backfills a winner harness (a frozen ``terminus2_agent`` source package) to
ALL 25 CPU-only AutoLab tasks so it can be compared head-to-head against the
optimization-time baseline (which was already scored on the same 25 tasks).

Already-scored tasks can be reused from a prior result's ``score_breakdown``
(``--reuse <result.json>``) so we only spend harbor time on the missing tasks.
The held-out-test convention is best-of-n with ``n>=2`` to kill single-roll
noise — pass ``--n-attempts 2``.

Usage:
  set -a && source .env && set +a
  python scripts/eval_autolab_cpu25_compare.py \
      --name designer_opus_winner \
      --src runs/.../designer/checkpoints/<ckpt>/terminus2_agent \
      --reuse runs/.../designer/test/candidate_results/designer_test_<ckpt>.json \
      --out runs/cpu25_compare/designer_opus_winner \
      --n-attempts 2 --workers 10 \
      --env-file /tmp/worldcalib_solver_env_20260609_145901.env

Omit ``--reuse`` to score every CPU task fresh (e.g. the nowmc winner, whose
prior 10-task scores were n=1 train and must be re-measured at n>=2).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _cpu_task_ids(tasks_root: Path) -> list[str]:
    from worldcalib.autolab.autolab import load_autolab_tasks

    tasks = load_autolab_tasks(tasks_root)
    return sorted(t.task_id for t in tasks if t.gpus == 0)


def _reuse_scores(reuse_path: Path | None) -> dict[str, dict]:
    """Return {task_id: {score, passed}} from a prior result's score_breakdown."""
    if reuse_path is None:
        return {}
    d = json.loads(reuse_path.read_text())
    sb = d.get("score_breakdown") or {}
    out: dict[str, dict] = {}
    for tid, rec in sb.items():
        if tid == "all" or not isinstance(rec, dict):
            continue
        out[tid] = {
            "score": float(rec.get("average_score", 0.0) or 0.0),
            "passed": bool(rec.get("passrate", 0.0) >= 1.0),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    root = _project_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="candidate id / display name")
    ap.add_argument("--src", required=True, type=Path,
                    help="path to the terminus2_agent source package")
    ap.add_argument("--out", required=True, type=Path, help="output dir")
    ap.add_argument("--reuse", type=Path, default=None,
                    help="prior result.json to reuse already-scored tasks from")
    ap.add_argument("--task-ids", default=None,
                    help="comma-separated task ids; default = all 25 CPU tasks")
    ap.add_argument("--tasks-path", type=Path,
                    default=root / "third_party" / "autolab" / "tasks")
    ap.add_argument("--n-attempts", type=int, default=2)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--model", default="openai/deepseek-v4-flash")
    ap.add_argument("--harbor-binary", type=Path,
                    default=Path("/data/home/yuhan/cyh_dev/bin/harbor"))
    ap.add_argument("--harbor-python", type=Path,
                    default=Path("/data/home/yuhan/cyh_dev/bin/python"))
    ap.add_argument("--env-file", type=Path, default=None,
                    help="solver env-file (OPENAI_API_KEY/BASE_URL for the target)")
    ap.add_argument("--eval-timeout-s", type=int, default=20000)
    args = ap.parse_args(argv)

    from worldcalib.autolab.autolab import (
        AutolabHarborRunner,
        DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        load_autolab_tasks,
    )

    src = args.src.resolve()
    if not (src / "terminus_2").is_dir():
        raise SystemExit(f"--src has no terminus_2 package: {src}")

    if args.task_ids:
        want = [t.strip() for t in args.task_ids.split(",") if t.strip()]
    else:
        want = _cpu_task_ids(args.tasks_path)
    print(f"[plan] full CPU set: {len(want)} tasks")

    reuse = _reuse_scores(args.reuse)
    reuse = {k: v for k, v in reuse.items() if k in want}
    todo = [t for t in want if t not in reuse]
    print(f"[plan] reuse {len(reuse)} already-scored, eval {len(todo)} fresh "
          f"(n={args.n_attempts}, {args.workers}-way): {todo}")

    fresh_rows: dict[str, dict] = {}
    if todo:
        tasks = load_autolab_tasks(args.tasks_path, task_ids=tuple(todo))
        args.out.mkdir(parents=True, exist_ok=True)
        runner = AutolabHarborRunner(
            tasks=tasks,
            out_dir=args.out,
            harbor_binary=args.harbor_binary,
            harbor_python=args.harbor_python,
            harbor_agent="terminus-2",
            harbor_model=args.model,
            n_attempts=args.n_attempts,
            timeout_multiplier=1.0,
            concurrency=1,
            env_file=args.env_file,
            reward_gate=0.5,
            score_mode="best",
            eval_timeout_s=args.eval_timeout_s,
            max_eval_workers=args.workers,
            verify_patches=False,
        )
        candidate = {
            "name": args.name,
            "agent_source_path": str(src),
            "scaffold_name": DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        }
        result = runner.evaluate_candidate(
            candidate=candidate,
            candidate_id=args.name,
            agent_name=DEFAULT_AUTOLAB_SCAFFOLD_NAME,
        )
        for t in result.task_results:
            fresh_rows[t.task_id] = {"score": float(t.score), "passed": bool(t.passed)}

    merged: dict[str, dict] = {}
    for tid in want:
        if tid in fresh_rows:
            merged[tid] = {**fresh_rows[tid], "source": "fresh"}
        elif tid in reuse:
            merged[tid] = {**reuse[tid], "source": "reuse"}
        else:
            merged[tid] = {"score": None, "passed": None, "source": "MISSING"}

    scored = [v["score"] for v in merged.values() if v["score"] is not None]
    passed = [v["passed"] for v in merged.values() if v["passed"] is not None]
    avg = sum(scored) / len(scored) if scored else 0.0
    passrate = sum(1 for p in passed if p) / len(passed) if passed else 0.0

    summary = {
        "name": args.name,
        "src": str(src),
        "n_attempts": args.n_attempts,
        "task_count": len(want),
        "scored_count": len(scored),
        "average_score": round(avg, 4),
        "passrate": round(passrate, 4),
        "per_task": {k: {"score": (round(v["score"], 4) if v["score"] is not None else None),
                         "passed": v["passed"], "source": v["source"]}
                     for k, v in sorted(merged.items())},
    }
    out_json = args.out / f"{args.name}_cpu25.json"
    args.out.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n[done] {args.name}: avg={avg:.4f} passrate={passrate:.3f} "
          f"over {len(scored)}/{len(want)} tasks -> {out_json}")
    miss = [k for k, v in merged.items() if v["source"] == "MISSING"]
    if miss:
        print(f"[warn] {len(miss)} tasks unscored: {miss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
