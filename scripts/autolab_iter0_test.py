#!/usr/bin/env python
"""AutoLab iter-0 smoke test: run the plain terminus-2 baseline on ONE cheap
CPU-only task through harbor and print the parsed reward + score_breakdown.

The task is chosen as the cheapest CPU-only task in the catalog (gpus == 0,
lowest agent timeout, then lowest verifier timeout) so the smoke run is as quick
as possible. ``toy_isa_opt`` (7200s agent + 120s verifier, CPU-only) is the
default.

ALL docker-invoking code is guarded behind ``__main__`` so importing this module
never launches anything.

Usage (real run — launches a harbor docker task, takes minutes):
    set -a && source .env && set +a
    python scripts/autolab_iter0_test.py [--task-id <id>] [--out <dir>] [--model <m>]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _pick_cheapest_cpu_task(tasks_path: Path) -> str:
    """Return the cheapest CPU-only task id (gpus==0), by (agent, verifier) timeout."""

    from worldcalib.autolab.autolab import load_autolab_tasks

    tasks = load_autolab_tasks(tasks_path)
    cpu_tasks = [t for t in tasks if t.gpus == 0]
    if not cpu_tasks:
        raise RuntimeError("no CPU-only AutoLab tasks found")
    cpu_tasks.sort(
        key=lambda t: (t.agent_timeout_sec, t.verifier_timeout_sec, t.task_id)
    )
    return cpu_tasks[0].task_id


def main(argv: list[str] | None = None) -> int:
    root = _project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tasks-path",
        type=Path,
        default=root / "third_party" / "autolab" / "tasks",
    )
    parser.add_argument(
        "--task-id",
        default="",
        help="Task id to run; empty = pick the cheapest CPU-only task.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "runs" / "autolab_iter0_smoke",
    )
    parser.add_argument("--model", default="deepseek-v4-pro[1m]")
    parser.add_argument("--harbor-binary", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--timeout-multiplier", type=float, default=1.0)
    parser.add_argument(
        "--no-patch-check",
        dest="verify_patches",
        action="store_false",
        help="Skip the cyh_dev harbor patch verification.",
    )
    parser.set_defaults(verify_patches=True)
    args = parser.parse_args(argv)

    from worldcalib.autolab.autolab import (
        DEFAULT_HARBOR_BINARY,
        AutolabHarborRunner,
        load_autolab_tasks,
    )

    task_id = args.task_id or _pick_cheapest_cpu_task(args.tasks_path)
    tasks = load_autolab_tasks(args.tasks_path, task_ids=(task_id,))
    if not tasks:
        raise SystemExit(f"task id not found: {task_id}")
    task = tasks[0]
    print(
        f"[autolab-iter0] running baseline terminus-2 on {task.task_id} "
        f"(domain={task.domain}, gpus={task.gpus}, "
        f"agent_timeout={task.agent_timeout_sec}s, verifier={task.verifier_timeout_sec}s)"
    )

    candidate = {
        "name": "terminus2_autolab",
        "scaffold_name": "terminus2_autolab",
        "agent_name": "terminus2_autolab",
        "model": args.model,
        "agent_kwargs": {},
        "agent_env": {},
    }
    runner = AutolabHarborRunner(
        tasks=tasks,
        out_dir=args.out,
        harbor_binary=args.harbor_binary or DEFAULT_HARBOR_BINARY,
        harbor_model=args.model,
        n_attempts=1,
        timeout_multiplier=args.timeout_multiplier,
        concurrency=1,
        env_file=args.env_file,
        reward_gate=0.5,
        max_eval_workers=1,
        force=True,
        verify_patches=args.verify_patches,
    )
    result = runner.evaluate_candidate(
        candidate=candidate,
        candidate_id="autolab_iter0_smoke",
        agent_name="terminus2_autolab",
    )
    result_payload = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
    print("[autolab-iter0] candidate result:")
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print("[autolab-iter0] score_breakdown:")
    print(json.dumps(result_payload["score_breakdown"], indent=2, ensure_ascii=False))
    print("[autolab-iter0] per-task:")
    for task_row in result_payload["tasks"]:
        print(
            f"  {task_row['task_id']}: reward={task_row['score']:.4f} "
            f"passed={task_row['passed']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
