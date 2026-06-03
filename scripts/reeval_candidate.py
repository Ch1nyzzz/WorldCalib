#!/usr/bin/env python3
"""Re-evaluate a stored candidate with the CURRENT target/judge to detect drift.

Reads a candidate's spec from a run's runstore.db, rebuilds its scaffold from
the on-disk source snapshot, and re-runs the full LongMemEval eval + judge
exactly as the optimizer would. Prints the fresh passrate so it can be compared
against the historically recorded one — a large gap means the external
deepseek target/judge API drifted, not that the proposer got unlucky.

Usage:
  set -a && source .env && set +a
  python scripts/reeval_candidate.py <run_dir> <iteration> [--source-run <dir>]

--source-run rewrites the candidate's source_project_path into that run dir
(use the BACKUP when re-evaluating an iteration whose snapshot was truncated).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from worldcalib.dynamic import load_candidate_scaffold
from worldcalib.evaluation import EvaluationRunner
from worldcalib.scaffolds.base import ScaffoldConfig
from worldcalib.memory.longmemeval import (
    LongMemEvalJudge,
    load_longmemeval_examples,
    prepare_longmemeval,
    select_split,
)
from worldcalib.memory.longmemeval import default_split_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("iteration", type=int)
    ap.add_argument("--source-run", type=Path, default=None,
                    help="rewrite source_project_path into this run dir")
    ap.add_argument("--variant", default="s")
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--base-url", default="https://api.deepseek.com")
    ap.add_argument("--judge-model", default="deepseek-v4-flash")
    ap.add_argument("--judge-base-url", default="https://api.deepseek.com")
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--timeout-s", type=int, default=300)
    args = ap.parse_args()

    db = args.run_dir / "runstore.db"
    c = sqlite3.connect(db)
    row = c.execute(
        "select candidate_id, scaffold_name, config_json from candidates where iteration=?",
        (args.iteration,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"no candidate at iteration {args.iteration} in {db}")
    candidate_id, scaffold_name, config_json = row
    cfg = json.loads(config_json)
    extra = dict(cfg.get("extra") or {})

    # Optionally repoint the source snapshot to a different (e.g. BACKUP) run.
    if args.source_run is not None:
        spp = extra.get("source_project_path", "")
        # the path embeds ".../proposer_calls/iter_NNN/source_snapshot/..."
        marker = "/proposer_calls/"
        if marker in spp:
            tail = spp[spp.index(marker):]
            extra["source_project_path"] = str(args.source_run) + tail
        extra["candidate_root"] = str(args.source_run / "generated")

    name = candidate_id.split("_", 1)[1] if "_" in candidate_id else candidate_id
    # strip the trailing _topN the optimizer appends to candidate_id
    raw = {
        "name": scaffold_name if scaffold_name else name,
        "scaffold_name": extra.get("scaffold_name", "memgpt_source"),
        "top_k": int(cfg.get("top_k", 8)),
        "window": int(cfg.get("window", 1)),
        "extra": extra,
        "source_project_path": extra.get("source_project_path"),
        "source_family": extra.get("source_family", "memgpt"),
    }
    print(f"re-evaluating {candidate_id}")
    print(f"  source_project_path: {extra.get('source_project_path')}")
    print(f"  target={args.model}@{args.base_url}  judge={args.judge_model}@{args.judge_base_url}")

    project_root = Path(__file__).resolve().parents[1]
    scaffold = load_candidate_scaffold(raw, project_root=project_root)

    # examples — train split, same as the run
    examples = load_longmemeval_examples(data_path=None, variant=args.variant)
    examples = select_split(examples, split="train", variant=args.variant,
                            split_path=default_split_path(args.variant))
    print(f"  train tasks: {len(examples)}")

    judge_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not judge_key:
        raise SystemExit("DEEPSEEK_API_KEY not set (source .env)")
    score_run = LongMemEvalJudge(
        model=args.judge_model, base_url=args.judge_base_url,
        api_key=judge_key, timeout_s=args.timeout_s,
    ).score_run

    config = ScaffoldConfig(top_k=raw["top_k"], window=raw["window"], extra=extra)
    with tempfile.TemporaryDirectory() as tmp:
        runner = EvaluationRunner(
            examples=examples, out_dir=Path(tmp),
            model=args.model, base_url=args.base_url, api_key="EMPTY",
            timeout_s=args.timeout_s, dry_run=False, max_context_chars=6000,
            max_eval_workers=args.workers, score_run=score_run, force=True,
        )
        res = runner.evaluate_scaffold(
            scaffold=scaffold, scaffold_name=raw["name"],
            config=config, candidate_id=candidate_id,
        )
    print(f"\n=== RESULT ===")
    print(f"  fresh passrate     : {round(res.passrate,4)}")
    print(f"  fresh average_score: {round(res.average_score,4)}")
    print(f"  tasks counted      : {res.count}")


if __name__ == "__main__":
    main()
