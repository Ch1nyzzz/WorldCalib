"""Mechanical scoring of a calib-variant proposer's two-sided prediction.

The ``calib`` proposer variant asks the proposer to predict, BEFORE evaluation,
which question types its candidate will IMPROVE (``## Upside``) and which it
might REGRESS (``## Downside``), relative to a declared ``## Base`` iteration.
After the candidate is evaluated we compare those predictions to the real
per-question-type passrate change (from each candidate's ``score_breakdown``)
and produce objective metrics:

* **upside hit rate** — of the types predicted to improve, how many actually did
* **downside recall** — of the types that actually regressed, how many were named
* **surprise regressions** — types that regressed but were NOT named (blind spots)
* **net-bet direction** — did the overall passrate Δ sign match "upside > downside"

These are deliberately set-membership / direction metrics, not a numeric MAE:
the proposer is graded on getting the *direction and the affected types* right,
not on guessing exact passrates (which the user judged unrealistic to predict).
They (a) drive the prediction-accuracy learning curve and (b) ground the
critic's written grade in :mod:`worldcalib.optimizer`.

Pure / dependency-free so it is unit-testable in isolation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# A per-type passrate change beyond ±this (vs the declared base) counts as a
# real improvement / regression. Matches the threshold documented in the skill.
IMPROVE_EPS = 0.02
REGRESS_EPS = 0.02


@dataclass
class ParsedPrediction:
    """The machine-readable content of a calib ``prediction.md``."""

    base_raw: str | None  # e.g. "iter_7", "clean", or None if absent
    base_iter: int | None  # parsed iteration number, or None for clean/absent
    upside: set[str]  # predicted-to-improve question-type labels (lowercased)
    downside: set[str]  # predicted-to-regress question-type labels (lowercased)
    net_delta: tuple[float | None, float | None]  # overall Δ interval [lo, hi]


def _section_body(text: str, header_keyword: str) -> str:
    """Return the body of the first ``## <...header_keyword...>`` section.

    Matches on a case-insensitive keyword in the header so it tolerates the
    parenthetical hints in the template (e.g. ``## Upside — question types …``).
    Body runs until the next ``## `` heading or end of text.
    """
    lines = text.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.lstrip().startswith("## "):
            if capturing:
                break
            capturing = header_keyword.lower() in line.lower()
            continue
        if capturing:
            out.append(line)
    return "\n".join(out)


def _bullet_labels(body: str) -> set[str]:
    """Extract the leading label of each ``- <label>: …`` bullet, lowercased."""
    labels: set[str] = set()
    for line in body.splitlines():
        m = re.match(r"\s*[-*]\s*`?([^:`]+?)`?\s*:", line)
        if not m:
            continue
        label = m.group(1).strip().lower()
        # skip the template placeholder rows
        if label and not label.startswith("<") and label != "…":
            labels.add(label)
    return labels


def parse_prediction(text: str) -> ParsedPrediction:
    """Parse a calib ``prediction.md`` into structured fields."""
    base_body = _section_body(text, "base")
    base_raw: str | None = None
    base_iter: int | None = None
    # the proposer may put the value in the header parens or the body; scan both
    scan = base_body
    header_match = re.search(r"^##\s*Base[^\n]*", text, re.IGNORECASE | re.MULTILINE)
    if header_match:
        scan = header_match.group(0) + "\n" + base_body
    m_iter = re.search(r"iter[_\s]?(\d+)", scan, re.IGNORECASE)
    if m_iter:
        base_iter = int(m_iter.group(1))
        base_raw = f"iter_{base_iter}"
    elif re.search(r"\bclean\b", scan, re.IGNORECASE):
        base_raw = "clean"

    upside = _bullet_labels(_section_body(text, "upside"))
    downside = _bullet_labels(_section_body(text, "downside"))

    net_body = _section_body(text, "net bet")
    lo = hi = None
    m_int = re.search(r"\[\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\]", net_body)
    if m_int:
        lo, hi = float(m_int.group(1)), float(m_int.group(2))

    return ParsedPrediction(
        base_raw=base_raw,
        base_iter=base_iter,
        upside=upside,
        downside=downside,
        net_delta=(lo, hi),
    )


def _passrate(entry) -> float | None:
    if isinstance(entry, dict):
        v = entry.get("passrate")
        return float(v) if v is not None else None
    if isinstance(entry, (int, float)):
        return float(entry)
    return None


def per_type_deltas(
    candidate_breakdown: dict, parent_breakdown: dict
) -> dict[str, float]:
    """Per-question-type passrate(candidate) − passrate(parent)."""
    out: dict[str, float] = {}
    for qtype, entry in candidate_breakdown.items():
        cp = _passrate(entry)
        pp = _passrate(parent_breakdown.get(qtype))
        if cp is None or pp is None:
            continue
        out[qtype] = round(cp - pp, 6)
    return out


def _match_key(label: str, keys: list[str]) -> str | None:
    """Map a predicted label to an actual score_breakdown key.

    Exact match first, then substring either direction (so a prediction of
    "temporal" matches the key "temporal-reasoning", and vice versa).
    """
    label = label.strip().lower()
    lk = {k.lower(): k for k in keys}
    if label in lk:
        return lk[label]
    for low, orig in lk.items():
        if label in low or low in label:
            return orig
    return None


def score_prediction(
    pred: ParsedPrediction, deltas: dict[str, float]
) -> dict:
    """Score a parsed prediction against the realized per-type deltas.

    Returns a JSON-serialisable dict of the four headline metrics plus the
    supporting detail (matched/unmatched labels, the actual improved/regressed
    type sets, and the realized overall Δ when derivable from the deltas).
    """
    keys = list(deltas.keys())
    improved = {k for k, d in deltas.items() if d > IMPROVE_EPS}
    regressed = {k for k, d in deltas.items() if d < -REGRESS_EPS}

    pred_up = {k for k in (_match_key(l, keys) for l in pred.upside) if k}
    pred_down = {k for k in (_match_key(l, keys) for l in pred.downside) if k}

    upside_hits = pred_up & improved
    upside_hit_rate = (len(upside_hits) / len(pred_up)) if pred_up else None

    downside_caught = pred_down & regressed
    downside_recall = (len(downside_caught) / len(regressed)) if regressed else None

    surprise_regressions = sorted(regressed - pred_down)

    overall_delta = (
        round(sum(deltas.values()) / len(deltas), 6) if deltas else None
    )
    # net-bet direction: the proposer always bets "upside > downside" (it chose
    # to propose); correct iff the realized overall Δ is non-negative.
    net_bet_correct = (overall_delta is not None and overall_delta >= -REGRESS_EPS)

    return {
        "upside_hit_rate": upside_hit_rate,
        "downside_recall": downside_recall,
        "n_surprise_regressions": len(surprise_regressions),
        "surprise_regressions": surprise_regressions,
        "net_bet_correct": net_bet_correct,
        "overall_delta": overall_delta,
        "predicted_upside": sorted(pred_up),
        "predicted_downside": sorted(pred_down),
        "actually_improved": sorted(improved),
        "actually_regressed": sorted(regressed),
        "unmatched_upside_labels": sorted(
            l for l in pred.upside if not _match_key(l, keys)
        ),
        "unmatched_downside_labels": sorted(
            l for l in pred.downside if not _match_key(l, keys)
        ),
        "base_raw": pred.base_raw,
        "base_iter": pred.base_iter,
    }


# --- run-dir helpers (used by the optimizer; thin, side-effecting) -----------

def load_score_breakdown(result_path: Path) -> dict:
    """Read a candidate_results/*.json and return its ``score_breakdown``."""
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d.get("score_breakdown") or {}


def evaluate_prediction(
    prediction_text: str,
    candidate_breakdown: dict,
    parent_breakdown: dict,
) -> dict:
    """End-to-end: parse + delta + score. Returns the metrics dict (+ deltas)."""
    pred = parse_prediction(prediction_text)
    deltas = per_type_deltas(candidate_breakdown, parent_breakdown)
    metrics = score_prediction(pred, deltas)
    metrics["per_type_deltas"] = deltas
    return metrics


if __name__ == "__main__":  # quick self-test
    sample_pred = """# iter_5 prediction
## Candidate (one line)
query-biased compression
## Base (which prior iter's stack this builds on)
builds on iter_2 stack
## Mechanism
keep query-relevant sentences
## Upside — question types this should IMPROVE (and why)
- temporal-reasoning: denser evidence surfaces dates
- multi-session: less truncation across sessions
## Downside — question types that might REGRESS (and why)
- single-session-preference: short answers may lose the cue
## Net bet
- Overall train passrate Δ: [+0.02, +0.06]
- Why upside > downside: most failures are truncation-driven
## Falsification
if temporal does not move, the mechanism is wrong
"""
    parent = {
        "temporal-reasoning": {"passrate": 0.30, "count": 26},
        "multi-session": {"passrate": 0.45, "count": 27},
        "single-session-preference": {"passrate": 0.25, "count": 4},
        "knowledge-update": {"passrate": 0.90, "count": 15},
    }
    cand = {
        "temporal-reasoning": {"passrate": 0.42, "count": 26},  # +0.12 improved (predicted)
        "multi-session": {"passrate": 0.46, "count": 27},  # +0.01 flat (predicted up, missed)
        "single-session-preference": {"passrate": 0.10, "count": 4},  # -0.15 regressed (predicted)
        "knowledge-update": {"passrate": 0.80, "count": 15},  # -0.10 surprise regression
    }
    out = evaluate_prediction(sample_pred, cand, parent)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["base_iter"] == 2
    assert out["upside_hit_rate"] == 0.5  # temporal hit, multi-session missed
    assert out["downside_recall"] == 0.5  # ssp caught, knowledge-update missed
    assert out["surprise_regressions"] == ["knowledge-update"]
    assert out["net_bet_correct"] is False  # mean delta = (-0.03) < 0
    print("\nself-test OK")
