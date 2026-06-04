"""Evaluate a stored tau2 candidate scaffold on a domain's TEST split.

The optimizer only ever scores candidates on the TRAIN split (30 tasks). To
check whether a "best on train" candidate actually generalizes, this re-runs one
stored candidate's edited scaffold over the held-out TEST split (the next
``test_size`` ordinal tasks after train for domains without named splits — 67
for banking_knowledge: tasks 30..96 of 97).

It loads the candidate exactly the way the optimizer's eval loop does — from the
iteration's ``pending_eval.json`` via
``load_candidate_tau2_scaffold`` (source-backed: imports the EDITED
``PassthroughTau2Scaffold`` from the iteration's ``source_snapshot``) — so the
scaffold under test is byte-identical to what produced the train score, only the
episode set changes.

Run from the tau2 eval venv (agentrl-free), with DEEPSEEK_API_KEY in env:

    set -a && source .env && set +a
    PYTHONPATH=src .venv-tau2-eval/bin/python scripts/tau2_test_eval.py \
        --iter-dir runs/<run>/proposer_calls/iter_006 \
        --domain banking_knowledge --train-size 30 --test-size 67 \
        --concurrency 32

The candidate's iteration dir is ``<run>/proposer_calls/iter_<NNN>``; its
``pending_eval.json`` carries the candidate metadata (kind, scaffold_name,
source_snapshot path). Prints the TEST passrate + per-question-type breakdown and
writes the full ``candidate_results/<id>.json`` under ``--out``.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_candidate_dict(iter_dir: Path) -> dict:
    """The first candidate from an iteration's pending_eval.json."""
    payload = json.loads((iter_dir / "pending_eval.json").read_text())
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError(f"no candidates in {iter_dir / 'pending_eval.json'}")
    return candidates[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--iter-dir",
        required=True,
        help="candidate iteration dir, e.g. runs/<run>/proposer_calls/iter_006",
    )
    ap.add_argument("--domain", default="banking_knowledge")
    ap.add_argument("--split", default="test", choices=("test", "train"))
    ap.add_argument("--train-size", type=int, default=30)
    ap.add_argument("--test-size", type=int, default=67)
    ap.add_argument("--agent-model", default="deepseek/deepseek-chat")
    ap.add_argument("--user-model", default="deepseek/deepseek-chat")
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument(
        "--out",
        default="",
        help="output dir for candidate_results/<id>.json (default: <iter-dir>/test_eval)",
    )
    args = ap.parse_args()

    from loguru import logger

    logger.remove()  # silence tau2's per-call logging

    from worldcalib.agentic.backends.tau2.data import load_tau2_examples
    from worldcalib.agentic.backends.tau2.dynamic import load_candidate_tau2_scaffold
    from worldcalib.agentic.backends.tau2.evaluation import Tau2EvaluationRunner
    from worldcalib.scaffolds.base import ScaffoldConfig

    iter_dir = Path(args.iter_dir).resolve()
    out_dir = Path(args.out).resolve() if args.out else (iter_dir / "test_eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    candidate = _load_candidate_dict(iter_dir)
    cand_name = candidate.get("name") or candidate.get("build_tag") or iter_dir.name
    print(f"candidate:   {cand_name}")
    print(f"iter dir:    {iter_dir}")
    print(f"split:       {args.split} (domain={args.domain})")

    scaffold = load_candidate_tau2_scaffold(candidate, project_root=REPO_ROOT)

    examples = load_tau2_examples(
        args.domain,
        args.split,
        train_size=args.train_size,
        test_size=args.test_size,
    )
    print(f"episodes:    {len(examples)}")

    runner = Tau2EvaluationRunner(
        examples=examples,
        out_dir=out_dir,
        domain=args.domain,
        agent_model=args.agent_model,
        user_model=args.user_model,
        concurrency=args.concurrency,
        runs=args.runs,
    )

    candidate_id = f"{cand_name}__{args.split}{len(examples)}"
    result = runner.evaluate_scaffold(
        scaffold=scaffold,
        scaffold_name=str(candidate.get("scaffold_name") or "tau2_passthrough"),
        config=ScaffoldConfig(),
        candidate_id=candidate_id,
    )

    result_path = out_dir / "candidate_results" / f"{candidate_id}.json"
    data = json.loads(result_path.read_text()) if result_path.exists() else {}
    tasks = data.get("tasks", [])
    statuses = Counter(t.get("metadata", {}).get("status", "?") for t in tasks)

    print(f"\n===== {cand_name} — {args.split.upper()} ({len(examples)} episodes) =====")
    print(f"  passrate:     {result.passrate:.4f}")
    print(f"  avg reward:   {result.average_score:.4f}")
    print(f"  status tally: {dict(statuses)}")
    print("  score_breakdown (per question_type):")
    for bucket, info in (data.get("score_breakdown") or {}).items():
        print(f"    {bucket}: {info}")
    print(f"\n  result json:  {result_path}")
    print("RUN OK")


if __name__ == "__main__":
    main()
