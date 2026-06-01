"""Deterministic, coarse calibration track record for the critic proposer.

The critic variant (``--proposer-variant critic``) replaces the prose
``world_model_calibration.md`` with two data-grounded signals:

* the RunStore *ledger* (queried live by the proposer / critic subagent), and
* this *track record* — a per-run scorecard of how well the proposer's own
  ``P(regress)`` calls matched the ledger's measured outcomes.

This module builds that scorecard. It is deliberately **not** a statistical
calibration scorer (no Brier, no reliability curve): the proposer cannot
predict exact passrates, so a precise score would be precision theatre. What
bites is the coarse, categorical fact — *"of the regressions that actually
happened, how many did you flag?"* — read from the ledger by code, never
narrated by the model.

The scorecard is rendered to ``calibration_track_record.md`` and staged into
the next iter's workspace (SKILL.md workflow step 0 reads it).

Run offline against any existing run to inspect / validate:

    python -m worldcalib.calibration_track_record runs/<run_id>
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

# A passrate change at or beyond this magnitude counts as a real move; smaller
# is treated as flat (noise band), matching the directional analysis used to
# evaluate the prose variant.
REGRESS_EPS = 0.03

_P_REGRESS_RE = re.compile(r"P\s*\(\s*regress\s*\)\s*:?\s*([01]?\.\d+|[01](?:\.0+)?)", re.IGNORECASE)
_DELTA_LINE_RE = re.compile(r"passrate\s*Δ\s*:\s*\[([^\]]+)\]", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"[+-]?\d*\.\d+")

# critique.md base rate: "→ P(regress|class) ≈ 0.30" (explicit decimal) or the
# "of N nearest: X regressed" tally it is computed from.
_BASE_RATE_RE = re.compile(
    r"P\s*\(\s*regress\s*\|\s*class\s*\)\s*[≈=:]+\s*([01]?\.\d+|[01](?:\.0+)?)",
    re.IGNORECASE,
)
_BASE_RATE_TALLY_RE = re.compile(
    r"of\s+(\d+)\s+nearest\s*:?\s*(\d+)\s+regressed", re.IGNORECASE
)
# critique.md verdict line: "## Verdict\n revise | proceed-with-justification"
_VERDICT_RE = re.compile(r"##\s*Verdict\s*\n+\s*([^\n]+)", re.IGNORECASE)


@dataclass(frozen=True)
class IterRecord:
    iteration: int
    p_regress: float | None          # proposer's stated P(regress), if any
    pred_delta_hi: float | None      # upper end of predicted passrate Δ, if any
    actual_passrate_delta: float | None  # ledger truth (vs parent)
    regression_count: int | None

    @property
    def actual_regressed(self) -> bool | None:
        if self.actual_passrate_delta is None:
            return None
        return self.actual_passrate_delta <= -REGRESS_EPS

    @property
    def predicted_regress(self) -> bool | None:
        """Did the proposer call a regression? Prefer the explicit P(regress);
        fall back to the sign of the predicted Δ interval (so the record is
        computable for the prose variant too)."""
        if self.p_regress is not None:
            return self.p_regress >= 0.5
        if self.pred_delta_hi is not None:
            return self.pred_delta_hi < 0
        return None


def parse_prediction_signals(text: str) -> tuple[float | None, float | None]:
    """Return ``(P(regress), predicted_Δ_high)`` parsed from a prediction.md."""
    p_regress: float | None = None
    m = _P_REGRESS_RE.search(text)
    if m:
        try:
            p_regress = float(m.group(1))
        except ValueError:
            p_regress = None
    delta_hi: float | None = None
    dm = _DELTA_LINE_RE.search(text)
    if dm:
        nums = _DECIMAL_RE.findall(dm.group(1))
        if len(nums) >= 2:
            delta_hi = float(nums[1])
    return p_regress, delta_hi


def parse_critique_signals(text: str) -> tuple[float | None, str | None]:
    """Return ``(base_rate, verdict)`` parsed from a critique.md.

    ``base_rate`` is the critic's reference-class P(regress|class): the explicit
    decimal if present, else computed from the ``of N nearest: X regressed``
    tally. ``verdict`` is normalized to ``"revise"`` or ``"proceed"`` (or None
    if absent). These feed the enforced critic gate: a candidate whose stated
    ``P(regress)`` undercuts ``base_rate`` (optimism discount) or whose verdict
    is ``revise`` is rejected when ``critic_gate_enforce`` is on.
    """
    base_rate: float | None = None
    m = _BASE_RATE_RE.search(text)
    if m:
        try:
            base_rate = float(m.group(1))
        except ValueError:
            base_rate = None
    if base_rate is None:
        tm = _BASE_RATE_TALLY_RE.search(text)
        if tm:
            n_total = int(tm.group(1))
            n_regressed = int(tm.group(2))
            if n_total > 0:
                base_rate = n_regressed / n_total

    verdict: str | None = None
    vm = _VERDICT_RE.search(text)
    if vm:
        line = vm.group(1).lower()
        # "proceed-with-justification" contains neither bare token ambiguity;
        # check revise first since some lines read "revise (not proceed)".
        if "revise" in line:
            verdict = "revise"
        elif "proceed" in line:
            verdict = "proceed"
    return base_rate, verdict


def _prediction_path(run_dir: Path, iteration: int) -> Path:
    return run_dir / "proposer_calls" / f"iter_{iteration:03d}" / "workspace" / "prediction.md"


def read_ledger_outcomes(runstore_db: Path) -> dict[int, dict]:
    """Map iteration -> {passrate_delta, regression_count, breakthrough_count}."""
    out: dict[int, dict] = {}
    if not runstore_db.exists():
        return out
    with sqlite3.connect(runstore_db) as conn:
        conn.row_factory = sqlite3.Row
        for r in conn.execute(
            "SELECT iteration, passrate_delta, regression_count, breakthrough_count "
            "FROM proposal_outcomes ORDER BY iteration"
        ):
            out[int(r["iteration"])] = {
                "passrate_delta": r["passrate_delta"],
                "regression_count": r["regression_count"],
                "breakthrough_count": r["breakthrough_count"],
            }
    return out


def collect_records(run_dir: Path) -> list[IterRecord]:
    """Join each iter's prediction.md signals to the ledger's measured outcome."""
    outcomes = read_ledger_outcomes(run_dir / "runstore.db")
    records: list[IterRecord] = []
    for iteration in sorted(outcomes):
        pred_path = _prediction_path(run_dir, iteration)
        p_regress = delta_hi = None
        if pred_path.is_file():
            p_regress, delta_hi = parse_prediction_signals(pred_path.read_text(encoding="utf-8"))
        o = outcomes[iteration]
        records.append(
            IterRecord(
                iteration=iteration,
                p_regress=p_regress,
                pred_delta_hi=delta_hi,
                actual_passrate_delta=o["passrate_delta"],
                regression_count=o["regression_count"],
            )
        )
    return records


def summarize(records: list[IterRecord]) -> dict:
    """Coarse confusion matrix over iters where both a call and an outcome exist."""
    scored = [r for r in records if r.predicted_regress is not None and r.actual_regressed is not None]
    tp = sum(1 for r in scored if r.predicted_regress and r.actual_regressed)
    fn = sum(1 for r in scored if not r.predicted_regress and r.actual_regressed)
    fp = sum(1 for r in scored if r.predicted_regress and not r.actual_regressed)
    tn = sum(1 for r in scored if not r.predicted_regress and not r.actual_regressed)
    actual_regressions = tp + fn
    return {
        "n_scored": len(scored),
        "actual_regressions": actual_regressions,
        "regressions_flagged": tp,
        "regressions_missed": fn,
        "false_alarms": fp,
        "true_negatives": tn,
        "recall": (tp / actual_regressions) if actual_regressions else None,
        "uses_p_regress": any(r.p_regress is not None for r in scored),
    }


def render_markdown(records: list[IterRecord], *, last_k: int = 8) -> str:
    s = summarize(records)
    lines: list[str] = ["# Calibration track record", ""]
    if s["n_scored"] == 0:
        lines.append("No scored iterations yet — make a prediction with `P(regress)`.")
        return "\n".join(lines) + "\n"

    basis = "your stated P(regress)" if s["uses_p_regress"] else "the sign of your predicted Δ (no P(regress) on file)"
    recall = s["recall"]
    recall_str = f"{s['regressions_flagged']}/{s['actual_regressions']}" if s["actual_regressions"] else "n/a (no regressions yet)"
    lines += [
        f"Scored on {s['n_scored']} past iterations, using {basis}.",
        "",
        "## Your regression calls vs reality",
        f"- Real regressions (passrate dropped ≥ {REGRESS_EPS:.2f} vs parent): **{s['actual_regressions']}**",
        f"- Of those, you flagged (P(regress)≥0.5 / predicted Δ<0): **{recall_str}**"
        + (f"  → recall {recall:.0%}" if recall is not None else ""),
        f"- Regressions you MISSED: **{s['regressions_missed']}**",
        f"- False alarms (you predicted regress, it improved/held): **{s['false_alarms']}**",
        "",
    ]
    if s["actual_regressions"] and (recall is None or recall < 0.5):
        lines += [
            "> **You are under-calling regressions.** Raise `P(regress)` when the "
            "reference class (trace_similar) shows similar changes regressed — do "
            "not default to optimism.",
            "",
        ]

    recent = records[-last_k:]
    lines += ["## Recent iterations (most recent last)", "",
              "| iter | P(regress) | predicted Δ_hi | actual Δ | regressed? | call |",
              "|---|---|---|---|---|---|"]
    for r in recent:
        pr = f"{r.p_regress:.2f}" if r.p_regress is not None else "—"
        dh = f"{r.pred_delta_hi:+.2f}" if r.pred_delta_hi is not None else "—"
        ad = f"{r.actual_passrate_delta:+.2f}" if r.actual_passrate_delta is not None else "—"
        reg = "—" if r.actual_regressed is None else ("YES" if r.actual_regressed else "no")
        if r.predicted_regress is None or r.actual_regressed is None:
            call = "—"
        elif r.predicted_regress and r.actual_regressed:
            call = "✓ flagged"
        elif not r.predicted_regress and r.actual_regressed:
            call = "✗ MISSED"
        elif r.predicted_regress and not r.actual_regressed:
            call = "false alarm"
        else:
            call = "✓ ok"
        lines.append(f"| {r.iteration} | {pr} | {dh} | {ad} | {reg} | {call} |")
    return "\n".join(lines) + "\n"


def write_track_record(run_dir: Path, *, last_k: int = 8) -> Path:
    """Build and write ``<run_dir>/calibration_track_record.md``; return its path."""
    records = collect_records(run_dir)
    md = render_markdown(records, last_k=last_k)
    out = run_dir / "calibration_track_record.md"
    out.write_text(md, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the calibration track record for a run.")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--last-k", type=int, default=8)
    ap.add_argument("--print", action="store_true", help="print to stdout instead of writing the file")
    args = ap.parse_args(argv)
    records = collect_records(args.run_dir)
    md = render_markdown(records, last_k=args.last_k)
    if args.print:
        sys.stdout.write(md)
    else:
        out = args.run_dir / "calibration_track_record.md"
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
