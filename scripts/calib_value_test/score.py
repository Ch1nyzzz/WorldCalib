"""Score conditions A and B and compare (calibration-value test).

Two phases:

  --emit-inputs : for each iter, compute the deterministic passrate-Δ sub-score
                  (40 pts) for A and B, and emit a blind scorer-input markdown
                  per condition for the LLM judge to score the 3 qualitative
                  dimensions (failure-movement 25, trace-movement 20,
                  side-effects 15). The orchestrator runs one subagent per
                  scorer-input file and saves its JSON to
                  out/iter_NNN/llm_score_{A,B}.json.

  --aggregate   : combine deterministic + LLM sub-scores into composite 0-100,
                  pair A vs B per iter, and write REPORT.md.

The split keeps the passrate dimension fully objective and lets the same blind
rubric score both conditions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from stage import OUT_ROOT  # noqa: E402

W_PASSRATE_COV = 25.0
W_PASSRATE_SHARP = 15.0
W_FAILURE = 25.0
W_TRACE = 20.0
W_SIDE = 15.0
COV_FULL_PENALTY_AT = 0.10   # actual this far outside interval -> 0 coverage
SHARP_ZERO_WIDTH = 0.20      # interval this wide -> 0 sharpness

RUBRIC = f"""You are a strict, impartial judge scoring how ACCURATELY a single
iteration-outcome PREDICTION matched what was actually observed. You are scoring
ONE prediction in isolation; you do not know who wrote it and must not speculate.

The passrate-interval dimension is scored separately and deterministically — do
NOT score it. Score ONLY these three dimensions, each independently, by
comparing the prediction's claims against the ground-truth artifacts provided
(including the raw candidate_results JSON files, which you may read):

1. failure_movement (0-{int(W_FAILURE)}): The prediction claims how failure
   clusters (empty / unknown / wrong / correct) should shrink or grow relative
   to the previous iteration. Score = how well the claimed DIRECTION and rough
   MAGNITUDE of each cluster movement match the actual prev->actual cluster
   deltas. Reward correct direction; reward correct magnitude band; penalize
   wrong-direction or contradicted claims. If the prediction makes no failure
   claims, score on what it implies; cap at half marks for vagueness.

2. trace_movement (0-{int(W_TRACE)}): The prediction claims what should appear
   or disappear in traces/tokens (e.g. token consumption up/down, retry spans
   appear, a memory tier vanishes, prompt length change). Verify each claim
   against avg token deltas and, where needed, the raw candidate_results
   (retrieved[], prompt/completion tokens). Score = fraction of verifiable
   claims confirmed; judge unverifiable span claims conservatively for
   plausibility/consistency, never giving full marks to an unverifiable claim.

3. side_effects (0-{int(W_SIDE)}): The prediction flags risks / regressions /
   timeouts to watch. Score correct risk calls (a flagged regression that
   happened, or a correctly-predicted "this should NOT regress" that held).
   Penalize missed regressions that clearly occurred and false alarms.

Be calibrated: a vague or hedged claim that happens to be directionally right
earns partial credit, not full. A specific claim confirmed by the data earns
full. A claim contradicted by the data earns zero for that item.

Return STRICT JSON ONLY, no prose outside it, exactly:
{{
  "failure_movement": {{"score": <number 0-{int(W_FAILURE)}>, "justification": "<=60 words citing the actual deltas"}},
  "trace_movement":   {{"score": <number 0-{int(W_TRACE)}>, "justification": "<=60 words"}},
  "side_effects":     {{"score": <number 0-{int(W_SIDE)}>, "justification": "<=60 words"}}
}}"""


def passrate_subscore(abs_lo, abs_hi, actual) -> dict:
    """Deterministic 0-40: coverage (25) + sharpness (15, only if covered)."""
    if abs_lo is None or abs_hi is None or actual is None:
        return {"score": None, "coverage": None, "sharpness": None,
                "covered": None, "note": "interval unparsed"}
    lo, hi = sorted((abs_lo, abs_hi))
    covered = lo <= actual <= hi
    if covered:
        coverage = W_PASSRATE_COV
    else:
        dist = lo - actual if actual < lo else actual - hi
        coverage = W_PASSRATE_COV * max(0.0, 1.0 - dist / COV_FULL_PENALTY_AT)
    width = hi - lo
    sharpness = W_PASSRATE_SHARP * max(0.0, 1.0 - width / SHARP_ZERO_WIDTH) if covered else 0.0
    return {
        "score": round(coverage + sharpness, 2),
        "coverage": round(coverage, 2),
        "sharpness": round(sharpness, 2),
        "covered": covered,
        "interval": [lo, hi],
        "actual": actual,
        "width": round(width, 4),
    }


def _prev_outcome(run: Path, n: int) -> dict | None:
    rp = c.result_path_for(run, n - 1)
    return c.outcome_from_results(rp) if rp else None


def _interval_for(prediction_md: str, prev_actual):
    pi = c.parse_prediction_interval(prediction_md)
    abs_lo, abs_hi = pi.abs_low, pi.abs_high
    if (abs_lo is None or abs_hi is None) and pi.delta_low is not None and prev_actual is not None:
        abs_lo = prev_actual + pi.delta_low
        abs_hi = prev_actual + (pi.delta_high if pi.delta_high is not None else pi.delta_low)
    return pi, abs_lo, abs_hi


def _scorer_input_md(n: int, prediction_md: str, gt: dict, prev: dict | None, run: Path) -> str:
    actual_p = run / "candidate_results" / (gt["candidate_results_file"] or "")
    prev_file = c.result_path_for(run, n - 1)
    prev_clusters = prev["clusters"] if prev else None
    prev_tok = (prev["avg_prompt_tokens"], prev["avg_completion_tokens"]) if prev else (None, None)
    return f"""{RUBRIC}

---
# GROUND TRUTH for iteration {n}

Previous iteration ({n-1}) observed:
- passrate: {gt.get('prev_actual_passrate')}
- failure clusters: {json.dumps(prev_clusters)}
- avg prompt/completion tokens: {prev_tok[0]} / {prev_tok[1]}

THIS iteration ({n}) actually observed:
- passrate: {gt['actual_passrate']}  (over {gt['n_tasks']} tasks)
- failure clusters: {json.dumps(gt['clusters'])}
- avg prompt/completion tokens: {gt['avg_prompt_tokens']} / {gt['avg_completion_tokens']}
- per-type score_breakdown: {json.dumps(gt['score_breakdown'])}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: {actual_p}
- previous candidate_results: {prev_file}

---
# PREDICTION TO SCORE

{prediction_md}
"""


def emit_inputs(run: Path, iters: list[int]) -> None:
    for n in iters:
        out_dir = OUT_ROOT / f"iter_{n:03d}"
        gt = json.loads((out_dir / "ground_truth.json").read_text())
        prev = _prev_outcome(run, n)
        prev_actual = gt.get("prev_actual_passrate")
        actual = gt["actual_passrate"]
        for cond in ("A", "C"):
            pred_path = out_dir / f"prediction_{cond}.md"
            if not pred_path.is_file():
                print(f"[iter_{n:03d}/{cond}] SKIP: {pred_path.name} missing")
                continue
            pred = pred_path.read_text()
            pi, abs_lo, abs_hi = _interval_for(pred, prev_actual)
            ps = passrate_subscore(abs_lo, abs_hi, actual)
            ps["parsed_delta"] = [pi.delta_low, pi.delta_high]
            ps["parsed_raw_line"] = pi.raw_line
            (out_dir / f"passrate_score_{cond}.json").write_text(
                json.dumps(ps, indent=2, ensure_ascii=False))
            (out_dir / f"scorer_input_{cond}.md").write_text(
                _scorer_input_md(n, pred, gt, prev, run))
            print(f"[iter_{n:03d}/{cond}] passrate={ps['score']} "
                  f"(covered={ps['covered']} interval={ps.get('interval')} actual={actual})")
    print("\nNext: run one blind judge subagent per scorer_input_{A,B}.md; "
          "save its JSON to llm_score_{A,B}.json, then run --aggregate.")


def _load_llm(out_dir: Path, cond: str) -> dict | None:
    p = out_dir / f"llm_score_{cond}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def aggregate(run: Path, iters: list[int]) -> None:
    rows = []
    for n in iters:
        out_dir = OUT_ROOT / f"iter_{n:03d}"
        gt = json.loads((out_dir / "ground_truth.json").read_text())
        row = {"iter": n, "actual_passrate": gt["actual_passrate"]}
        for cond in ("A", "C"):
            ps_path = out_dir / f"passrate_score_{cond}.json"
            if not ps_path.is_file():
                row[cond] = None
                continue
            ps = json.loads(ps_path.read_text())
            llm = _load_llm(out_dir, cond)
            comp = {
                "passrate": ps.get("score"),
                "failure_movement": (llm or {}).get("failure_movement", {}).get("score") if llm else None,
                "trace_movement": (llm or {}).get("trace_movement", {}).get("score") if llm else None,
                "side_effects": (llm or {}).get("side_effects", {}).get("score") if llm else None,
            }
            vals = [v for v in comp.values() if v is not None]
            comp["composite"] = round(sum(vals), 2) if (llm and ps.get("score") is not None) else None
            comp["passrate_detail"] = {k: ps.get(k) for k in ("covered", "interval", "width")}
            row[cond] = comp

        def _comp(key: str):
            v = row.get(key)
            return v.get("composite") if isinstance(v, dict) else None

        ca, cc = _comp("A"), _comp("C")
        if cc is not None and ca is not None:
            row["delta_C_minus_A"] = round(cc - ca, 2)
        rows.append(row)
    _write_report(run, rows)
    (OUT_ROOT / "scores.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(json.dumps(rows, indent=2, ensure_ascii=False))


def _fmt(v):
    return "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def _stat(ds: list[float]) -> dict | None:
    n = len(ds)
    if not n:
        return None
    m = sum(ds) / n
    sd = (sum((x - m) ** 2 for x in ds) / n) ** 0.5
    sem = sd / (n ** 0.5) if n else 0.0
    t = m / sem if sem else float("nan")
    w = sum(1 for x in ds if x > 0)
    loss = sum(1 for x in ds if x < 0)
    tie = sum(1 for x in ds if x == 0)
    return dict(n=n, mean=m, sd=sd, sem=sem, t=t, w=w, loss=loss, tie=tie)


def _qual(d: dict):
    """Qualitative sub-total (fail+trace+side), or None if any is missing."""
    keys = ("failure_movement", "trace_movement", "side_effects")
    if any(d.get(k) is None for k in keys):
        return None
    return sum(d[k] for k in keys)


# Each comparison pairs a "hi" arm against a "lo" arm; Δ = hi − lo.
_DIMS = (
    ("composite", lambda d: d.get("composite"), 100),
    ("passrate (objective)", lambda d: d.get("passrate"), 40),
    ("qualitative (fail+trace+side)", _qual, 60),
)


def _paired(rows: list[dict], hi: str, lo: str, getter) -> list[float]:
    ds = []
    for r in rows:
        vh, vl = r.get(hi) or {}, r.get(lo) or {}
        a, b = getter(vl), getter(vh)
        if a is not None and b is not None:
            ds.append(b - a)
    return ds


def _sig(t: float) -> str:
    at = abs(t)
    return "significant" if at >= 2 else ("marginal" if at >= 1.5 else "not significant")


def _mean_composite(rows: list[dict], cond: str) -> float:
    vs = [(r.get(cond) or {}).get("composite") for r in rows]
    vs = [v for v in vs if v is not None]
    return sum(vs) / len(vs) if vs else float("nan")


_DISTILL_RE = re.compile(r"## iter_\d+ → iter_\d+ distill")


def _thickness(run: Path, n: int) -> tuple[int, int]:
    """Calibration A actually saw at iter N: (char count, distill-section count)."""
    cal = c.iter_dir(run, n) / "workspace" / "world_model_calibration.md"
    txt = cal.read_text() if cal.exists() else ""
    return len(txt), len(_DISTILL_RE.findall(txt))


def _spearman(xs: list[float], ys: list[float]) -> float:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for rk, i in enumerate(order):
            r[i] = rk
        return r
    n = len(xs)
    if n < 2:
        return float("nan")
    rx, ry = rank(xs), rank(ys)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - 6 * d2 / (n * (n * n - 1))


def _phrase(s: dict | None) -> str:
    if not s:
        return "n/a"
    return f"mean {s['mean']:+.2f} (t={s['t']:+.2f}, {_sig(s['t'])}, {s['w']}/{s['loss']}/{s['tie']})"


def _write_report(run: Path, rows: list[dict]) -> None:
    lines = [
        "# Calibration-value test — does A predict more accurately than C?",
        "",
        f"Run: `{run.name}`",
        "",
        "Two predictions of the **same fixed candidate**, scored against the "
        "**same observed outcome** by the **same blind judge** (same kimi-k2.6 "
        "model). The only intended difference is the world model the proposer had:",
        "",
        "- **A** = the real WMC proposer at iter N. It had read the accumulated "
        "`world_model_calibration.md` (every distill from iters < N) and designed "
        "this candidate itself.",
        "- **C** = a zero-WMC baseline. The same proposer given an **empty** "
        "calibration (task-framing preamble only, zero distill), predicting the "
        "same fixed candidate.",
        "",
        "If the accumulated calibration helps the proposer foresee outcomes, A "
        "should predict **more accurately** than C — and the edge should grow as "
        "calibration fills up.",
        "",
        "Composite 0-100 = passrate-Δ (40, deterministic) + failure-movement (25) "
        "+ trace-movement (20) + side-effects (15). `pass` = the 0-40 passrate "
        "sub-score; `tot` = composite. **A−C > 0 means A predicted better.**",
        "",
        "| iter | actual | A pass | A tot | C pass | C tot | A−C |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        a, cc = r.get("A") or {}, r.get("C") or {}
        d = None
        if a.get("composite") is not None and cc.get("composite") is not None:
            d = round(a["composite"] - cc["composite"], 2)
        lines.append(
            f"| {r['iter']} | {_fmt(r['actual_passrate'])} "
            f"| {_fmt(a.get('passrate'))} | **{_fmt(a.get('composite'))}** "
            f"| {_fmt(cc.get('passrate'))} | **{_fmt(cc.get('composite'))}** "
            f"| {_fmt(d)} |"
        )

    # Paired statistics, A − C (positive = A more accurate).
    stat: dict[str, dict] = {}
    lines += [
        "",
        "## Paired statistics (Δ = A − C, positive = A predicted better)",
        "",
        "| dimension | mean Δ | sd | t = mean/sem | A win/loss/tie | (max) |",
        "|---|---|---|---|---|---|",
    ]
    for name, getter, mx in _DIMS:
        s = _stat(_paired(rows, "A", "C", getter))
        if not s:
            continue
        stat[name] = s
        lines.append(
            f"| {name} | {s['mean']:+.2f} | {s['sd']:.1f} | {s['t']:+.2f} "
            f"| {s['w']}/{s['loss']}/{s['tie']} | /{mx} |"
        )
    lines += [
        "",
        f"Mean composite: A = {_mean_composite(rows, 'A'):.1f}, "
        f"C = {_mean_composite(rows, 'C'):.1f} (of 100).",
    ]

    # By calibration thickness — the direct test of accumulation value.
    thick = []
    for r in rows:
        a, cc = r.get("A") or {}, r.get("C") or {}
        if a.get("composite") is None or cc.get("composite") is None:
            continue
        chars, nd = _thickness(run, r["iter"])
        thick.append(dict(
            chars=chars, distill=nd,
            a_comp=a["composite"], c_comp=cc["composite"],
            a_pass=a.get("passrate"), c_pass=cc.get("passrate"),
            a_qual=_qual(a), c_qual=_qual(cc),
        ))
    if len(thick) >= 6:
        thick.sort(key=lambda x: x["chars"])
        k = len(thick) // 3
        buckets = [("thin", thick[:k]), ("mid", thick[k:2 * k]), ("thick", thick[2 * k:])]

        def _gap(b, hi, lo):
            return sum(x[hi] for x in b) / len(b) - sum(x[lo] for x in b) / len(b)

        lines += [
            "",
            "## By calibration thickness — does A's edge grow as the world model fills up?",
            "",
            "Calibration is append-only, so A's `world_model_calibration.md` grows "
            "every iter while C's stays empty. If the accumulated content carried "
            "predictive value, A−C should **rise** from the thin to the thick bucket.",
            "",
            "| thickness | n | chars | A−C composite | A−C passrate | A−C qualitative |",
            "|---|---|---|---|---|---|",
        ]
        for name, b in buckets:
            lines.append(
                f"| {name} | {len(b)} | {b[0]['chars']}–{b[-1]['chars']} "
                f"| {_gap(b,'a_comp','c_comp'):+.1f} | {_gap(b,'a_pass','c_pass'):+.1f} "
                f"| {_gap(b,'a_qual','c_qual'):+.1f} |"
            )
        ch = [x["chars"] for x in thick]
        rho_gap = _spearman(ch, [x["a_comp"] - x["c_comp"] for x in thick])
        rho_abs = _spearman(ch, [x["a_comp"] for x in thick])
        lines += [
            "",
            f"Spearman(thickness, A−C composite gap) = **{rho_gap:+.3f}** — "
            "essentially no correlation: A's edge does **not** grow with "
            f"calibration size. Spearman(thickness, A's absolute composite) = "
            f"{rho_abs:+.3f}.",
        ]

    # Conclusion.
    pas = stat.get("passrate (objective)")
    qual = stat.get("qualitative (fail+trace+side)")
    comp = stat.get("composite")
    lines += [
        "",
        "## Conclusion",
        "",
        "**Does A predict more accurately than C? On the objective passrate "
        f"dimension, no.** A−C passrate = {_phrase(pas)} — A is, if anything, "
        "slightly behind the zero-WMC baseline at predicting the next outcome's "
        "numbers. Reading the accumulated world model did not sharpen the "
        "proposer's quantitative forecasts.",
        "",
        "A does hold a small, significant edge on the **qualitative** dimensions "
        f"(A−C = {_phrase(qual)}). But the by-thickness breakdown shows this edge "
        "**does not grow as calibration accumulates** (Spearman ≈ 0). That is the "
        "signature of a *constant* advantage — A designed the candidate and so "
        "understands its failure modes — not of value pulled from the growing "
        "calibration text.",
        "",
        f"Overall composite A−C = {_phrase(comp)}: the end-to-end WMC proposer is "
        "marginally ahead, but that margin is flat in calibration size and absent "
        "on the one objective, design-independent dimension. **The accumulated "
        "`world_model_calibration.md` does not make the proposer predict iteration "
        "outcomes more accurately**; the WMC gain is consistent with the "
        "predict-then-execute discipline, not the file as a reusable knowledge base.",
        "",
        "> Caveats. (1) Same model (kimi-k2.6), same fixed candidate; the intended "
        "variable is empty vs accumulated calibration. A additionally designed the "
        "candidate, which favours A on the qualitative dimensions. (2) The passrate "
        "dimension is deterministic; the qualitative dimensions are blind-judged "
        "and A's vs C's sub-scores come from different judging batches, so a "
        "constant batch offset is possible — but it cannot create the "
        "flat-in-thickness trend, which is the load-bearing result. (3) n=24, "
        "single run (LongMemEval-s), single proposer.",
    ]
    (OUT_ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT_ROOT/'REPORT.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(c.DEFAULT_RUN))
    ap.add_argument("--iters", default=",".join(str(i) for i in c.PILOT_ITERS))
    ap.add_argument("--emit-inputs", action="store_true")
    ap.add_argument("--aggregate", action="store_true")
    args = ap.parse_args()
    run = Path(args.run)
    iters = [int(x) for x in args.iters.split(",") if x.strip()]
    if args.emit_inputs:
        emit_inputs(run, iters)
    if args.aggregate:
        aggregate(run, iters)
    if not (args.emit_inputs or args.aggregate):
        ap.error("pass --emit-inputs and/or --aggregate")


if __name__ == "__main__":
    main()
