#!/usr/bin/env python3
"""Build the SWE-bench 15-task training subset + its iter-0 baseline dir.

The training set is 15 of the 19 issues the deepseek-v4-flash seed
(``mini_swe_agent_source``) *failed* on the calib_hard30 split, chosen for repo
diversity (all 8 repos covered). The baseline dir mirrors the layout the
optimizer's ``--baseline-dir`` reuse expects (run_summary.json + a
candidate_results/<id>.json), filtered to the 15 tasks so iter-0 starts at 0/15
without repaying any eval.

Reproducible: re-run any time to regenerate both artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DATA = ROOT / "data" / "swebench_train_calib_hard30.json"
SRC_BASE = ROOT / "runs" / "baseline_calib_hard30_deepseekv4flash_20260604_211001"
OUT_DATA = ROOT / "data" / "swebench_train_fail15.json"
OUT_BASE = ROOT / "runs" / "baseline_swebench_fail15"

# 15 of the 19 failed issues, repo-diverse (astropy1 django3 requests1 xarray2
# pylint2 pytest2 sphinx2 sympy2). Dropped: django-10554, django-11138,
# pylint-4604, pytest-5787.
FAIL15 = [
    "astropy__astropy-13398",
    "django__django-10097",
    "django__django-10973",
    "django__django-11400",
    "psf__requests-2931",
    "pydata__xarray-2905",
    "pydata__xarray-3993",
    "pylint-dev__pylint-4551",
    "pylint-dev__pylint-8898",
    "pytest-dev__pytest-10356",
    "pytest-dev__pytest-6197",
    "sphinx-doc__sphinx-11510",
    "sphinx-doc__sphinx-8548",
    "sympy__sympy-12489",
    "sympy__sympy-13852",
]

# Eval-gate path inside this repo (the baseline snapshot stored Optimizer1's
# absolute path; rewrite so the seed config is self-consistent in WorldCalib).
RUN_SCRIPT = ROOT / "scripts" / "run_miniswe_swebench_single.py"


def _instance_id(inst: dict) -> str:
    return str(inst.get("instance_id") or inst.get("task_id") or inst.get("id") or "")


def _score_breakdown(tasks: list[dict]) -> dict:
    n = len(tasks)
    breakdown = {
        "all": {
            "count": n,
            "passrate": (sum(1 for t in tasks if t.get("passed")) / n) if n else 0.0,
            "average_score": (sum(float(t.get("score", 0.0)) for t in tasks) / n) if n else 0.0,
        }
    }
    for t in tasks:
        breakdown[str(t["task_id"])] = {
            "count": 1,
            "passrate": 1.0 if t.get("passed") else 0.0,
            "average_score": float(t.get("score", 0.0)),
        }
    return breakdown


def _rewrite_config_paths(config: dict) -> dict:
    """Point the seed command/eval_command at this repo's eval-gate script."""
    config = dict(config)
    for key in ("command", "eval_command"):
        val = config.get(key)
        if isinstance(val, str) and "run_miniswe_swebench_single.py" in val:
            # Replace the leading "python <abs>/run_miniswe_swebench_single.py"
            # with this repo's script, keeping the run/eval subcommand + args.
            head, _, tail = val.partition("run_miniswe_swebench_single.py")
            config[key] = f"python {RUN_SCRIPT}{tail}"
    return config


def main() -> None:
    want = set(FAIL15)

    # 1) data subset -------------------------------------------------------
    data = json.loads(SRC_DATA.read_text(encoding="utf-8"))
    instances = data["instances"]
    subset = [i for i in instances if _instance_id(i) in want]
    found_ids = {_instance_id(i) for i in subset}
    missing = want - found_ids
    assert not missing, f"instances missing from calib_hard30: {sorted(missing)}"
    assert len(subset) == 15, f"expected 15, got {len(subset)}"
    OUT_DATA.write_text(
        json.dumps({"instances": subset}, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 2) baseline dir ------------------------------------------------------
    src_cand = json.loads(
        (SRC_BASE / "candidate_results" / "mini_swe_agent_source.json").read_text("utf-8")
    )
    tasks = [t for t in src_cand["tasks"] if str(t["task_id"]) in want]
    task_ids = {str(t["task_id"]) for t in tasks}
    assert task_ids == want, f"baseline tasks mismatch: missing {sorted(want - task_ids)}"

    n = len(tasks)
    passrate = sum(1 for t in tasks if t.get("passed")) / n
    average_score = sum(float(t.get("score", 0.0)) for t in tasks) / n
    prompt_tokens = sum(int(t.get("prompt_tokens", 0) or 0) for t in tasks)
    completion_tokens = sum(int(t.get("completion_tokens", 0) or 0) for t in tasks)
    token_consuming = prompt_tokens + completion_tokens

    cand = dict(src_cand["candidate"])
    cand["passrate"] = passrate
    cand["average_score"] = average_score
    cand["count"] = n
    cand["token_consuming"] = token_consuming
    cand["avg_token_consuming"] = token_consuming / n
    cand["avg_prompt_tokens"] = prompt_tokens / n
    cand["avg_completion_tokens"] = completion_tokens / n
    cand["config"] = _rewrite_config_paths(cand.get("config", {}))
    rel_result = "runs/baseline_swebench_fail15/candidate_results/mini_swe_agent_source.json"
    cand["result_path"] = rel_result

    (OUT_BASE / "candidate_results").mkdir(parents=True, exist_ok=True)
    payload = {
        "candidate": cand,
        "tasks": tasks,
        "score_breakdown": _score_breakdown(tasks),
    }
    (OUT_BASE / "candidate_results" / "mini_swe_agent_source.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    src_summary = json.loads((SRC_BASE / "run_summary.json").read_text("utf-8"))
    run_summary = dict(src_summary)
    run_summary["split"] = "train"
    run_summary["limit"] = 15
    run_summary["count"] = n
    run_summary["candidate_count"] = 1
    run_summary["candidates"] = [cand]
    run_summary.pop("pareto_frontier_path", None)
    (OUT_BASE / "run_summary.json").write_text(
        json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"wrote {OUT_DATA}  ({len(subset)} instances)")
    print(f"wrote {OUT_BASE}/  (iter0 passrate={passrate:.4f} over {n} tasks)")


if __name__ == "__main__":
    main()
