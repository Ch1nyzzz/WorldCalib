#!/usr/bin/env python3
"""Post-hoc calibration test: does the calib world-model make predictions
*more accurate* than no world-model at all?

Motivation
----------
The online calibration curve is confounded by selection bias (the proposer only
proposes optimistic patches near the frontier ceiling). And we already showed
that the WMC variant *without* a critic did NOT make predictions more accurate.
So the question that remains is the clean one:

    Given the calib-trained world model, are predictions more accurate than
    with *no* world model at all?

Design (two arms, only the world model differs)
-----------------------------------------------
For each kept candidate ``iter_k`` of a finished ``calib`` run we stage two
identical predictor sandboxes that see the SAME parent source snapshot, the
SAME diff, and the SAME base per-type passrate table. The only difference:

* ``no_wm``    — no world model file at all.
* ``calib_wm`` — the run's FINAL ``world_model_calibration.md`` with the
  ``## iter_k → iter_{k+1} distill`` block removed (leave-one-out, so the WM
  cannot open-book the candidate's own recorded outcome).

Each arm is a fresh, independent docker-kimi context (the SAME invocation mode
as the proposer / critic), predicts ONLY (no patch), and writes a two-sided
``prediction.md`` (Base / Mechanism / Upside / Downside / Net bet).

Scoring — pairwise BLIND judge (removes absolute-scale bias)
------------------------------------------------------------
Rather than score each arm against ground truth on an absolute scale, we hand a
judge BOTH predictions for the same candidate — anonymised to *Prediction A* /
*Prediction B* in a per-candidate randomised order — together with the
OBJECTIVE realised outcome (the mechanically-computed per-type deltas). The
judge (same docker-kimi, fresh context) returns ``WINNER: A|B|TIE``. We
de-anonymise and tally ``calib_wm``'s win-rate vs ``no_wm``.

Mechanical metrics (upside hit / downside recall / surprise regressions) are
also computed per arm via :mod:`worldcalib.prediction_feedback` as an objective
cross-check, but the headline result is the blind-judge win-rate.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make `worldcalib` importable when run straight from the repo.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from worldcalib.claude_runner import (  # noqa: E402
    ProposerSandboxConfig,
    run_code_agent_prompt,
)
from worldcalib.prediction_feedback import (  # noqa: E402
    evaluate_prediction,
    per_type_deltas,
)

# Extra env vars the docker-claude-kimi image / kimi proposer needs, on top of
# the runner's DEFAULT_DOCKER_ENV_VARS. The image derives ANTHROPIC_AUTH_TOKEN
# from KIMI_API_KEY, so that one must be passed through.
_KIMI_DOCKER_ENV = (
    "KIMI_API_KEY",
    "ENABLE_TOOL_SEARCH",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)

_DISTILL_HEADER = re.compile(r"^##\s*iter[_\s]?(\d+)\s*(?:→|->)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# run-dir introspection
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    iteration: int
    diff_path: Path
    source_snapshot: Path
    candidate_breakdown: dict
    base_raw: str  # "clean" or "iter_N"
    base_breakdown: dict
    stored_overall_delta: float | None  # from the online prediction_score event


def _load_breakdown(result_path: Path) -> dict:
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d.get("score_breakdown") or {}


def _locomo_category_map() -> dict[str, str]:
    """task_id -> LoCoMo question-type label, from the canonical loader."""
    from worldcalib.locomo import load_locomo_examples

    return {
        ex.task_id: (ex.metadata or {}).get("question_type")
        for ex in load_locomo_examples()
    }


def make_locomo_recompute_loader(catmap: dict[str, str]):
    """Build a breakdown loader that re-derives a per-question-type breakdown
    from each candidate_results file's per-task ``passed`` records.

    Older LoCoMo runs (pre per-category fix) only recorded an ``"all"`` bucket.
    The per-task results are intact, so we group them by question type (via the
    canonical task_id -> category map) and recompute per-type passrates. The
    mean over types reproduces the original ``all`` passrate exactly.
    """

    def loader(result_path: Path) -> dict:
        try:
            d = json.loads(Path(result_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        agg: dict[str, list] = {}
        for t in d.get("tasks") or []:
            qt = catmap.get(t.get("task_id")) or (t.get("metadata") or {}).get(
                "question_type"
            )
            if not qt:
                continue
            a = agg.setdefault(qt, [0, 0, 0.0])  # n, n_passed, score_sum
            a[0] += 1
            a[1] += 1 if t.get("passed") else 0
            a[2] += float(t.get("score") or 0.0)
        if not agg:  # nothing mappable — fall back to whatever was stored
            return d.get("score_breakdown") or {}
        return {
            qt: {
                "passrate": a[1] / a[0],
                "count": a[0],
                "average_score": a[2] / a[0],
            }
            for qt, a in agg.items()
        }

    return loader


def _prediction_events(run_dir: Path) -> dict[int, dict]:
    """iter -> the online prediction_score event (for base + delta validation)."""
    out: dict[int, dict] = {}
    summ = run_dir / "evolution_summary.jsonl"
    if not summ.is_file():
        return out
    for line in summ.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "prediction_score" and "iteration" in row:
            out[int(row["iteration"])] = row
    return out


def load_candidates(run_dir: Path, limit: int = 0, breakdown_loader=None) -> list[Candidate]:
    load_bd = breakdown_loader or _load_breakdown
    idx = json.loads((run_dir / "iteration_index.json").read_text(encoding="utf-8"))
    by_iter = {int(e["iteration"]): e for e in idx}
    events = _prediction_events(run_dir)

    def breakdown_for_iter(it: int) -> dict:
        entry = by_iter.get(it)
        if not entry:
            return {}
        paths = entry.get("candidate_result_paths") or []
        return load_bd(Path(paths[0])) if paths else {}

    out: list[Candidate] = []
    for it in sorted(by_iter):
        if it == 0:
            continue  # iter 0 is the seed baseline, not a proposed candidate
        entry = by_iter[it]
        diff_path = Path(entry.get("diff_path", ""))
        src = Path(entry.get("source_snapshot_dir", ""))
        if not diff_path.is_file() or not src.is_dir():
            continue
        cand_bd = breakdown_for_iter(it)
        if not cand_bd:
            continue
        ev = events.get(it, {})
        base_raw = ev.get("base_raw") or "clean"
        base_iter = ev.get("base_iter")
        if base_iter is not None:
            base_bd = breakdown_for_iter(int(base_iter))
            base_raw = f"iter_{int(base_iter)}"
        else:
            base_bd = breakdown_for_iter(0)  # clean seed baseline
            base_raw = "clean"
        if not base_bd:
            continue
        out.append(
            Candidate(
                iteration=it,
                diff_path=diff_path,
                source_snapshot=src,
                candidate_breakdown=cand_bd,
                base_raw=base_raw,
                base_breakdown=base_bd,
                stored_overall_delta=ev.get("overall_delta"),
            )
        )
        if limit and len(out) >= limit:
            break
    return out


def strip_distill(wm_text: str, k: int) -> str:
    """Remove every ``## iter_k → iter_* distill`` section (leave-one-out).

    Drops the block that directly records candidate ``iter_k``'s graded outcome
    so the world model cannot open-book the answer for the candidate it is being
    asked to predict.
    """
    out: list[str] = []
    skipping = False
    for line in wm_text.splitlines():
        if line.startswith("## "):
            m = _DISTILL_HEADER.match(line)
            skipping = bool(m and int(m.group(1)) == k)
            if skipping:
                continue
        if not skipping:
            out.append(line)
    return "\n".join(out)


def base_state_md(base_raw: str, base_breakdown: dict) -> str:
    rows = ["| question type | passrate | count |", "|---|---|---|"]
    for qt in sorted(base_breakdown):
        entry = base_breakdown[qt]
        pr = entry.get("passrate") if isinstance(entry, dict) else entry
        ct = entry.get("count") if isinstance(entry, dict) else "?"
        rows.append(f"| {qt} | {pr:.4f} | {ct} |" if pr is not None else f"| {qt} | ? | {ct} |")
    return (
        f"# Current scaffold state (base = {base_raw})\n\n"
        "These are the per-question-type passrates of the CURRENT scaffold "
        "(before the proposed diff). Predict the diff's effect RELATIVE to "
        "these numbers.\n\n" + "\n".join(rows) + "\n"
    )


def outcome_md(deltas: dict[str, float], improve_eps: float, regress_eps: float) -> str:
    improved = sorted(k for k, d in deltas.items() if d > improve_eps)
    regressed = sorted(k for k, d in deltas.items() if d < -regress_eps)
    overall = round(sum(deltas.values()) / len(deltas), 6) if deltas else None
    rows = ["| question type | actual Δ passrate |", "|---|---|"]
    for qt in sorted(deltas, key=lambda k: deltas[k]):
        rows.append(f"| {qt} | {deltas[qt]:+.4f} |")
    return (
        "# OBJECTIVE realised outcome (ground truth, measured after evaluation)\n\n"
        f"- Question types that ACTUALLY IMPROVED (Δ > +{improve_eps}): "
        f"{improved or 'none'}\n"
        f"- Question types that ACTUALLY REGRESSED (Δ < -{regress_eps}): "
        f"{regressed or 'none'}\n"
        f"- Overall mean Δ passrate: {overall:+.4f}\n\n" + "\n".join(rows) + "\n"
    )


# --------------------------------------------------------------------------- #
# docker-kimi invocation
# --------------------------------------------------------------------------- #
def build_sandbox(image: str, user: str, home: str) -> ProposerSandboxConfig:
    env = tuple(
        dict.fromkeys(ProposerSandboxConfig.docker_env_vars + _KIMI_DOCKER_ENV)
    )
    return ProposerSandboxConfig(
        kind="docker",
        docker_image=image,
        docker_workspace="/workspace",
        docker_env_vars=env,
        docker_mounts=(),
        docker_user=user,
        docker_home=home,
    )


@dataclass
class KimiConf:
    base_url: str
    auth_token: str
    model: str
    effort: str
    timeout_s: int
    sandbox: ProposerSandboxConfig


def run_agent(conf: KimiConf, prompt: str, cwd: Path, name: str) -> Any:
    cwd.mkdir(parents=True, exist_ok=True)
    return run_code_agent_prompt(
        prompt,
        agent="claude",
        cwd=cwd,
        log_dir=cwd,
        name=name,
        model=conf.model,
        effort=conf.effort,
        timeout_s=conf.timeout_s,
        sandbox=conf.sandbox,
        claude_base_url=conf.base_url,
        claude_auth_token=conf.auth_token,
    )


_PREDICT_PROMPT = (
    "You are a calibration PREDICTOR in a memory-scaffold optimization loop. "
    "Your ONLY job is to PREDICT — do NOT modify any code, do NOT run any "
    "evaluation, do NOT propose a patch.\n\n"
    "In your working directory you have:\n"
    "- `./source/` — the CURRENT memory scaffold source code (the base).\n"
    "- `./diff.patch` — a proposed change to that scaffold (NOT yet applied).\n"
    "- `./base_state.md` — the current per-question-type passrates of the base.\n"
    "{wm_line}"
    "\nRead them, reason about what `./diff.patch` mechanically changes in the "
    "retrieval/packing/prompting pipeline, and PREDICT which LongMemEval/LoCoMo "
    "question types it will IMPROVE and which it might REGRESS, relative to the "
    "base passrates.\n\n"
    "Write your prediction to `./prediction.md` with EXACTLY these sections:\n"
    "## Candidate (one line)\n"
    "## Base (which prior state this builds on — copy the base label)\n"
    "## Mechanism (what the diff changes, 1-3 sentences)\n"
    "## Upside — question types this should IMPROVE (and why)\n"
    "- <question-type label>: <one-line reason>\n"
    "## Downside — question types that might REGRESS (and why)\n"
    "- <question-type label>: <one-line reason>\n"
    "## Net bet\n"
    "- Overall passrate Δ: [<lo>, <hi>]\n"
    "- Why upside > downside: <one line>\n\n"
    "Use the EXACT question-type labels from `./base_state.md`. Be specific and "
    "honest about downside risk — naming a regression that then happens is "
    "rewarded; vague optimism is not."
)

_WM_LINE = (
    "- `./world_model.md` — accumulated calibration notes distilled from PRIOR "
    "experiments on this scaffold (which mechanisms helped/hurt which question "
    "types). Use it to inform your prediction.\n"
)

_JUDGE_PROMPT = (
    "You are an impartial judge comparing the ACCURACY of two predictions. Read "
    "`./judge_input.md` in your working directory. It contains, for ONE proposed "
    "scaffold change:\n"
    "- the OBJECTIVE realised outcome (which question types actually improved / "
    "regressed, measured after evaluation — this is ground truth);\n"
    "- two independent predictions of that change, anonymised as `Prediction A` "
    "and `Prediction B`.\n\n"
    "Decide which prediction was MORE ACCURATE about reality: it named the "
    "question types that truly moved (gains AND regressions), caught the real "
    "regressions rather than missing them, and got the overall net direction "
    "right. Penalise predictions that claimed improvements that did not happen "
    "or missed regressions that did. Judge ACCURACY only — not writing style or "
    "how good the patch was.\n\n"
    "Write your verdict to `./judge_verdict.md` with EXACTLY this shape:\n"
    "WINNER: <A|B|TIE>\n"
    "REASONING: <2-4 sentences: which types each got right/wrong vs the "
    "objective outcome, and why the winner is more accurate>\n"
)


def _read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


# --------------------------------------------------------------------------- #
# per-candidate pipeline
# --------------------------------------------------------------------------- #
def stage_arm(
    arm_cwd: Path, cand: Candidate, wm_text: str | None
) -> None:
    if arm_cwd.exists():
        shutil.rmtree(arm_cwd)
    arm_cwd.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        cand.source_snapshot,
        arm_cwd / "source",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(cand.diff_path, arm_cwd / "diff.patch")
    (arm_cwd / "base_state.md").write_text(
        base_state_md(cand.base_raw, cand.base_breakdown), encoding="utf-8"
    )
    if wm_text is not None:
        (arm_cwd / "world_model.md").write_text(wm_text, encoding="utf-8")


def process_candidate(
    conf: KimiConf,
    cand: Candidate,
    wm_loo_text: str,
    out_dir: Path,
    rng_seed: int,
    improve_eps: float,
    regress_eps: float,
) -> dict:
    base = out_dir / f"iter_{cand.iteration:03d}"
    arms = {
        "no_wm": (base / "no_wm", None),
        "calib_wm": (base / "calib_wm", wm_loo_text),
    }

    # --- 1. both predictor arms (sequential within a candidate) ------------- #
    preds: dict[str, str] = {}
    for arm, (cwd, wm) in arms.items():
        stage_arm(cwd, cand, wm)
        wm_line = _WM_LINE if wm is not None else ""
        prompt = _PREDICT_PROMPT.format(wm_line=wm_line)
        run_agent(conf, prompt, cwd, name=f"predict-{arm}")
        preds[arm] = _read_file(cwd / "prediction.md")

    # --- 2. mechanical cross-check (objective, per arm) --------------------- #
    deltas = per_type_deltas(cand.candidate_breakdown, cand.base_breakdown)
    mech: dict[str, dict] = {}
    for arm in arms:
        mech[arm] = evaluate_prediction(
            preds[arm], cand.candidate_breakdown, cand.base_breakdown
        ) if preds[arm].strip() else {}

    # --- 3. pairwise blind judge ------------------------------------------- #
    rng = random.Random(rng_seed + cand.iteration)
    arm_order = ["no_wm", "calib_wm"]
    rng.shuffle(arm_order)  # randomised A/B to cancel position bias
    label_to_arm = {"A": arm_order[0], "B": arm_order[1]}
    judge_cwd = base / "judge"
    judge_cwd.mkdir(parents=True, exist_ok=True)
    (judge_cwd / "judge_input.md").write_text(
        outcome_md(deltas, improve_eps, regress_eps)
        + "\n---\n\n## Prediction A\n\n"
        + (preds[label_to_arm["A"]].strip() or "(empty prediction)")
        + "\n\n---\n\n## Prediction B\n\n"
        + (preds[label_to_arm["B"]].strip() or "(empty prediction)")
        + "\n",
        encoding="utf-8",
    )
    run_agent(conf, _JUDGE_PROMPT, judge_cwd, name="judge")
    verdict_text = _read_file(judge_cwd / "judge_verdict.md")
    m = re.search(r"WINNER:\s*(A|B|TIE)", verdict_text, re.IGNORECASE)
    winner_label = m.group(1).upper() if m else "TIE"
    winner_arm = "tie" if winner_label == "TIE" else label_to_arm[winner_label]
    rm = re.search(r"REASONING:\s*(.+)", verdict_text, re.S)
    reason = (rm.group(1).strip() if rm else verdict_text.strip())[:1000]

    # consistency check vs the online-stored overall delta
    overall = round(sum(deltas.values()) / len(deltas), 6) if deltas else None
    delta_ok = (
        cand.stored_overall_delta is None
        or overall is None
        or abs(overall - cand.stored_overall_delta) < 1e-3
    )

    return {
        "iteration": cand.iteration,
        "base": cand.base_raw,
        "winner_arm": winner_arm,
        "winner_label": winner_label,
        "ab_order": {"A": label_to_arm["A"], "B": label_to_arm["B"]},
        "judge_reason": reason,
        "overall_delta_recomputed": overall,
        "overall_delta_stored": cand.stored_overall_delta,
        "overall_delta_consistent": delta_ok,
        "mechanical": {
            arm: {
                "upside_hit_rate": mech[arm].get("upside_hit_rate"),
                "downside_recall": mech[arm].get("downside_recall"),
                "n_surprise_regressions": mech[arm].get("n_surprise_regressions"),
                "net_bet_correct": mech[arm].get("net_bet_correct"),
                "predicted_upside": mech[arm].get("predicted_upside"),
                "predicted_downside": mech[arm].get("predicted_downside"),
            }
            for arm in arms
        },
        "actually_improved": sorted(k for k, d in deltas.items() if d > improve_eps),
        "actually_regressed": sorted(k for k, d in deltas.items() if d < -regress_eps),
    }


# --------------------------------------------------------------------------- #
# aggregation + main
# --------------------------------------------------------------------------- #
def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def summarize(rows: list[dict]) -> dict:
    wins = {"calib_wm": 0, "no_wm": 0, "tie": 0}
    for r in rows:
        wins[r["winner_arm"]] = wins.get(r["winner_arm"], 0) + 1
    n = len(rows)
    decided = wins["calib_wm"] + wins["no_wm"]

    def arm_mech(arm: str, key: str) -> float | None:
        return _mean([r["mechanical"][arm].get(key) for r in rows])

    return {
        "n_candidates": n,
        "judge_wins": wins,
        "calib_wm_win_rate_all": round(wins["calib_wm"] / n, 4) if n else None,
        "calib_wm_win_rate_decided": (
            round(wins["calib_wm"] / decided, 4) if decided else None
        ),
        "mechanical_means": {
            arm: {
                "upside_hit_rate": arm_mech(arm, "upside_hit_rate"),
                "downside_recall": arm_mech(arm, "downside_recall"),
                "n_surprise_regressions": arm_mech(arm, "n_surprise_regressions"),
            }
            for arm in ("no_wm", "calib_wm")
        },
        "delta_consistency_failures": [
            r["iteration"] for r in rows if not r["overall_delta_consistent"]
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0, help="cap #candidates (first-N)")
    ap.add_argument(
        "--sample",
        type=int,
        default=0,
        help="randomly sample this many candidates (seeded by --seed); "
        "takes precedence over --limit",
    )
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--improve-eps", type=float, default=0.02)
    ap.add_argument("--regress-eps", type=float, default=0.02)
    ap.add_argument(
        "--recompute-locomo-categories",
        action="store_true",
        help="re-derive per-question-type breakdowns from per-task records "
        "(for old LoCoMo runs that only stored an 'all' bucket)",
    )
    ap.add_argument("--docker-image", default="docker-claude-kimi:latest")
    ap.add_argument("--docker-home", default="/tmp")
    ap.add_argument("--docker-user", default=f"{os.getuid()}:{os.getgid()}")
    ap.add_argument("--model", default=os.environ.get("KIMI_MODEL", "kimi-k2.6"))
    ap.add_argument("--effort", default="max")
    ap.add_argument("--timeout-s", type=int, default=2400)
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"fatal: run dir not found: {run_dir}", file=sys.stderr)
        return 2

    kimi_key = os.environ.get("KIMI_API_KEY", "")
    if not kimi_key:
        print("fatal: KIMI_API_KEY not set (source .env)", file=sys.stderr)
        return 2
    if kimi_key.startswith("sk-kimi-"):
        base_url = os.environ.get("KIMI_BASE_URL", "https://api.kimi.com/coding")
    else:
        base_url = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/anthropic")
    # match the launchers' env contract for the docker-claude-kimi image
    os.environ.setdefault("ENABLE_TOOL_SEARCH", "false")
    for var in (
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        os.environ.setdefault(var, args.model)

    conf = KimiConf(
        base_url=base_url,
        auth_token=kimi_key,
        model=args.model,
        effort=args.effort,
        timeout_s=args.timeout_s,
        sandbox=build_sandbox(args.docker_image, args.docker_user, args.docker_home),
    )

    wm_late = _read_file(run_dir / "world_model_calibration.md")
    if not wm_late.strip():
        print("fatal: run has no world_model_calibration.md", file=sys.stderr)
        return 2

    bd_loader = None
    if args.recompute_locomo_categories:
        bd_loader = make_locomo_recompute_loader(_locomo_category_map())
        print("[posthoc] recomputing LoCoMo per-category breakdowns from tasks", flush=True)
    cands = load_candidates(
        run_dir, limit=0 if args.sample else args.limit, breakdown_loader=bd_loader
    )
    if not cands:
        print("fatal: no candidates found", file=sys.stderr)
        return 2
    if args.sample and args.sample < len(cands):
        picked = random.Random(args.seed).sample(cands, args.sample)
        cands = sorted(picked, key=lambda c: c.iteration)
        print(
            f"[posthoc] randomly sampled {len(cands)} of the run's candidates "
            f"(seed={args.seed}): iters {[c.iteration for c in cands]}",
            flush=True,
        )

    out_dir = args.out_dir or (_REPO_ROOT / "runs" / "_posthoc_calib" / run_dir.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"[posthoc] run={run_dir.name} candidates={len(cands)} "
        f"concurrency={args.concurrency} out={out_dir}",
        flush=True,
    )

    def work(cand: Candidate) -> dict:
        wm_loo = strip_distill(wm_late, cand.iteration)
        row = process_candidate(
            conf, cand, wm_loo, out_dir, args.seed,
            args.improve_eps, args.regress_eps,
        )
        print(
            f"[posthoc] iter {cand.iteration:>3} base={row['base']:<7} "
            f"winner={row['winner_arm']:<9} "
            f"(no_wm uhr={row['mechanical']['no_wm'].get('upside_hit_rate')} | "
            f"calib uhr={row['mechanical']['calib_wm'].get('upside_hit_rate')})",
            flush=True,
        )
        return row

    rows: list[dict] = []
    if args.concurrency <= 1:
        for cand in cands:
            rows.append(work(cand))
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futs = {pool.submit(work, c): c for c in cands}
            for fut in as_completed(futs):
                rows.append(fut.result())

    rows.sort(key=lambda r: r["iteration"])
    jsonl_path = out_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(rows)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n===== POST-HOC CALIBRATION SUMMARY =====", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"\nrows : {jsonl_path}\nsummary: {out_dir / 'summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
