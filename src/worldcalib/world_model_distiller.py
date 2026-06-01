"""Distil a cumulative, human-readable world model from the ledger.

This is the WMC document the critic variant maintains: a `world_model.md`
the proposer reads **before** proposing, so its very first candidate is
already informed by what worked, what regressed, and where the run is still
stuck. Unlike the old prose `world_model_calibration.md`, the proposer does
**not** write this — it is regenerated deterministically after every eval from
**measured** outcomes (the RunStore ledger), so it cannot be polluted by the
proposer's optimism. The lesson is read off real `passrate_delta`s and
per-question-type passrates, never narrated.

Inputs distilled (all already measured / scored against reality):
* trace (real outcomes): `proposal_outcomes.passrate_delta` per candidate, and
  per-question-type passrate from `candidate_results` — the proven stack,
  effective mechanisms, failure modes, and open problems.
* prediction (the proposer's bets), scored against the ledger: the calibration
  record (reused from :mod:`worldcalib.calibration_track_record`).

(Critic-claim distillation — which past challenges were validated — is a
future addition; the hook is the per-iter `critique.md`.)

Regenerate offline for any run:

    python -m worldcalib.world_model_distiller runs/<run_id>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from worldcalib.calibration_track_record import (
    REGRESS_EPS,
    collect_records,
    summarize,
)

# A question type at or below this passrate (in the best candidate) is flagged
# as an open problem worth a dedicated mechanism.
WEAK_QTYPE_PASSRATE = 0.35


def _ledger_rows(runstore_db: Path) -> list[dict]:
    """Per-iter rows joining candidate id/passrate to its parent-relative delta."""
    rows: list[dict] = []
    if not runstore_db.exists():
        return rows
    with sqlite3.connect(runstore_db) as conn:
        conn.row_factory = sqlite3.Row
        cand = {
            int(r["iteration"]): r
            for r in conn.execute(
                "SELECT iteration, candidate_id, passrate, result_path FROM candidates"
            )
        }
        outcomes = {
            int(r["iteration"]): r
            for r in conn.execute(
                "SELECT iteration, passrate_delta, regression_count FROM proposal_outcomes"
            )
        }
    for it in sorted(cand):
        c = cand[it]
        o = outcomes.get(it)
        rows.append(
            {
                "iteration": it,
                "candidate_id": c["candidate_id"],
                "passrate": c["passrate"],
                "result_path": c["result_path"],
                "passrate_delta": (o["passrate_delta"] if o else None),
                "regression_count": (o["regression_count"] if o else None),
            }
        )
    return rows


def _weak_question_types(run_dir: Path, best_result_path: str | None) -> list[tuple[str, float]]:
    """Per-question-type passrate of the best candidate, weakest first."""
    if not best_result_path:
        return []
    p = Path(best_result_path)
    if not p.is_absolute():
        p = run_dir / best_result_path
    if not p.is_file():
        # result_path may be run-relative or just a filename
        hits = list((run_dir / "candidate_results").glob(Path(best_result_path).name))
        if not hits:
            return []
        p = hits[0]
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    sb = d.get("score_breakdown") or {}
    out: list[tuple[str, float]] = []
    for qtype, v in sb.items():
        if isinstance(v, dict) and v.get("passrate") is not None:
            out.append((qtype, float(v["passrate"])))
    out.sort(key=lambda x: x[1])
    return out


def _vetoed_directions(run_dir: Path, limit: int = 8) -> list[dict]:
    """Candidates the critic gate rejected pre-eval, most recent first.

    These never reach the ledger (the loop discards a rejected iter before
    ``record_eval``), so without this they would be invisible to the next
    proposer — which could then re-propose the same vetoed direction. Read
    straight from the event log; deduped by candidate name/build_tag keeping
    the latest rejection.
    """
    summary = run_dir / "evolution_summary.jsonl"
    if not summary.is_file():
        return []
    seen: dict[str, dict] = {}
    for line in summary.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or '"critic_gate_rejected"' not in line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("event") != "critic_gate_rejected":
            continue
        cand = d.get("candidate") or {}
        label = cand.get("name") or cand.get("build_tag") or cand.get("scaffold_name")
        if not label:
            label = f"iter{d.get('iteration')}"
        seen[str(label)] = {
            "iteration": d.get("iteration"),
            "label": label,
            "reason": d.get("reject_reason"),
            "verdict": d.get("verdict"),
            "base_rate": d.get("base_rate"),
            "p_regress": d.get("p_regress"),
            "hypothesis": cand.get("hypothesis"),
        }
    rows = sorted(
        seen.values(),
        key=lambda r: (r["iteration"] is None, r["iteration"]),
        reverse=True,
    )
    return rows[:limit]


def render_world_model(run_dir: Path) -> str:
    rows = _ledger_rows(run_dir / "runstore.db")
    lines: list[str] = [
        "# World model (distilled from the ledger — read this BEFORE proposing)",
        "",
        "_Auto-generated after every eval from measured outcomes. Do NOT edit by "
        "hand; the proposer does not write this file. Use it to make your FIRST "
        "candidate already account for what worked, what regressed, and what is "
        "still stuck._",
        "",
    ]
    if not rows:
        lines.append("No iterations evaluated yet.")
        return "\n".join(lines) + "\n"

    scored = [r for r in rows if r["passrate"] is not None]
    best = max(scored, key=lambda r: r["passrate"]) if scored else None
    gains = sorted(
        (r for r in rows if (r["passrate_delta"] or 0) > REGRESS_EPS),
        key=lambda r: -(r["passrate_delta"] or 0),
    )
    regressions = sorted(
        (r for r in rows if (r["passrate_delta"] or 0) < -REGRESS_EPS),
        key=lambda r: (r["passrate_delta"] or 0),
    )

    # Proven stack
    lines += ["## Proven stack", ""]
    if best:
        lines.append(
            f"Best so far: **{best['candidate_id']}** at passrate "
            f"{best['passrate']:.2f} (iter {best['iteration']}). Build on this "
            f"unless you have a specific, falsifiable reason not to; state your "
            f"base candidate explicitly."
        )
    lines.append("")

    # Effective mechanisms
    lines += ["## Effective mechanisms (real gains vs parent — extend/combine these)", ""]
    if gains:
        for r in gains[:8]:
            lines.append(f"- +{r['passrate_delta']:.2f}  `{r['candidate_id']}`")
    else:
        lines.append("- (none yet)")
    lines.append("")

    # Failure modes
    lines += [
        "## Failure modes — AVOID (real regressions vs parent)",
        "",
        "These mechanisms regressed when tried. Do not repeat them unless your "
        "candidate specifically fixes the cause (and say how).",
        "",
    ]
    if regressions:
        for r in regressions[:8]:
            rc = r["regression_count"]
            rc_str = f"  ({rc} tasks regressed)" if rc is not None else ""
            lines.append(f"- {r['passrate_delta']:.2f}  `{r['candidate_id']}`{rc_str}")
    else:
        lines.append("- (none yet)")
    lines.append("")

    # Vetoed directions (critic gate rejected pre-eval — never hit the ledger)
    vetoed = _vetoed_directions(run_dir)
    if vetoed:
        lines += [
            "## Vetoed directions (critic gate rejected — do NOT re-propose)",
            "",
            "These candidates were blocked by the critic gate *before* eval, so "
            "they carry no passrate. Do not re-propose the same direction unless "
            "you directly resolve the critic's objection (raise `P(regress)` to "
            "at least the cited base rate, or address what made the verdict "
            "`revise`).",
            "",
        ]
        for r in vetoed:
            reason = r["reason"] or "rejected"
            detail = ""
            if reason == "optimism_discount" and r["p_regress"] is not None and r["base_rate"] is not None:
                detail = f" (P(regress) {r['p_regress']:.2f} < base rate {r['base_rate']:.2f})"
            elif reason == "verdict_revise":
                detail = " (critic verdict: revise)"
            hyp = r["hypothesis"]
            hyp_str = f" — {hyp[:140]}" if isinstance(hyp, str) and hyp.strip() else ""
            lines.append(f"- `{r['label']}` [{reason}{detail}]{hyp_str}")
        lines.append("")

    # Calibration record (prediction scored against the ledger)
    s = summarize(collect_records(run_dir))
    lines += ["## Your calibration record (past P(regress) vs reality)", ""]
    if s["n_scored"] == 0:
        lines.append("No scored predictions yet.")
    else:
        recall = s["recall"]
        recall_str = (
            f"{s['regressions_flagged']}/{s['actual_regressions']}"
            if s["actual_regressions"]
            else "n/a"
        )
        lines.append(
            f"Real regressions: {s['actual_regressions']} | you flagged: "
            f"{recall_str}"
            + (f" (recall {recall:.0%})" if recall is not None else "")
            + f" | false alarms: {s['false_alarms']}"
        )
        if s["actual_regressions"] and (recall is None or recall < 0.5):
            lines.append("")
            lines.append(
                "> **You under-call regressions.** When the reference class "
                "(trace_similar) shows a similar mechanism regressed, raise "
                "`P(regress)` toward that base rate instead of discounting it."
            )
    lines.append("")

    # Open problems
    weak = _weak_question_types(run_dir, best["result_path"] if best else None)
    open_probs = [(q, p) for q, p in weak if p <= WEAK_QTYPE_PASSRATE]
    lines += [
        "## Open problems (persistently weak question types — diagnose, do NOT special-case)",
        "",
    ]
    if open_probs:
        for q, p in open_probs:
            lines.append(f"- `{q}`: {p:.2f} in the best candidate")
        lines.append("")
        lines.append(
            "These are weak because of a **general** information-flow gap (retrieval "
            "coverage, evidence ordering, context budget, conflict handling) — treat "
            "them as a diagnostic signal, not a to-do list. Do NOT build a "
            "question-type-specific rule, detector, or branch to attack them: "
            "per-type special-casing (temporal/numerical/answer-type handlers, "
            "month-name enrichment, inference pre-computation) is overfitting and "
            "has repeatedly regressed here. Fix the underlying general mechanism so "
            "the whole frontier moves; if the weak type does not improve as a side "
            "effect of a stronger general mechanism, that is informative, not a cue "
            "to special-case it."
        )
    else:
        lines.append("- (best candidate is reasonably balanced across question types)")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_world_model(run_dir: Path) -> Path:
    out = run_dir / "world_model.md"
    out.write_text(render_world_model(run_dir), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Distil world_model.md from a run's ledger.")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args(argv)
    md = render_world_model(args.run_dir)
    if args.print:
        sys.stdout.write(md)
    else:
        out = args.run_dir / "world_model.md"
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
