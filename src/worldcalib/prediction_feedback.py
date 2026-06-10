"""Mechanical scoring of a calib-variant proposer's PER-TASK prediction.

The calib proposer predicts, BEFORE evaluation, the concrete per-task effect of
its change: which specific ``task_id``s it expects to flip ``fail->pass`` or
``pass->fail`` (relative to a declared ``## Base`` iteration), each tied to that
task's trace. After the candidate is evaluated we compare those named flips to
the REAL per-task flips (candidate ``tasks[]`` vs the base iter's ``tasks[]``)
and produce objective metrics:

* **flip hit rate** — of the flips predicted, how many actually flipped as called
* **blind-spot regressions** — tasks that flipped pass->fail but were NOT named
* **false flips** — predicted to flip but did not

We deliberately do NOT score aggregate passrate or per-category score deltas:
predicting a number rewards optimism and is unfalsifiable, and selecting on it
caused optimizer's-curse mis-picks. Per-task flips are concrete and checkable.

Pure / dependency-free so it is unit-testable in isolation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Direction tokens for a per-task flip.
F2P = "fail->pass"
P2F = "pass->fail"
PROT = "protected"
# Honest-ceiling token: the proposer is 100% certain no harness change can solve
# this task (a fundamental model-capability gap). Predicts the task STAYS fail;
# being overruled (it later flips to pass) is an over-pessimism error.
LIMITED = "model-limited"

# Tolerant arrow matchers: accept unicode → or ascii -> / ->>, any spacing.
_F2P_RE = re.compile(r"fail\s*(?:→|-+>?)\s*pass", re.IGNORECASE)
_P2F_RE = re.compile(r"pass\s*(?:→|-+>?)\s*fail", re.IGNORECASE)


@dataclass
class ParsedPrediction:
    """The machine-readable content of a calib ``prediction.md``."""

    base_raw: str | None  # e.g. "iter_7", "clean", or None if absent
    base_iter: int | None  # parsed iteration number, or None for clean/absent
    per_task: dict[str, str] = field(default_factory=dict)  # task_id -> F2P|P2F|PROT


def _section_body(text: str, header_keyword: str) -> str:
    """Return the body of the first ``## <...header_keyword...>`` section.

    Matches on a case-insensitive keyword in the header so it tolerates the
    parenthetical hints in the template (e.g. ``## Per-task effects — …``).
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


def _parse_base(text: str) -> tuple[str | None, int | None]:
    base_body = _section_body(text, "base")
    scan = base_body
    header_match = re.search(r"^##\s*Base[^\n]*", text, re.IGNORECASE | re.MULTILINE)
    if header_match:
        scan = header_match.group(0) + "\n" + base_body
    m_iter = re.search(r"iter[_\s]?(\d+)", scan, re.IGNORECASE)
    if m_iter:
        n = int(m_iter.group(1))
        return f"iter_{n}", n
    if re.search(r"\bclean\b", scan, re.IGNORECASE):
        return "clean", None
    return None, None


def parse_prediction(text: str) -> ParsedPrediction:
    """Parse a calib ``prediction.md`` into structured per-task fields."""
    base_raw, base_iter = _parse_base(text)

    per_task: dict[str, str] = {}
    # The flips live under "## Per-task effects"; the honest-ceiling tasks live
    # under "## Model-limited". Parse bullets from both sections.
    body = (
        _section_body(text, "per-task")
        + "\n"
        + _section_body(text, "model-limited")
    )
    for line in body.splitlines():
        # task_ids can contain ``::`` (e.g. LONGMEMEVAL::s::af082822), so split
        # on the first colon FOLLOWED BY WHITESPACE — the real ``id: direction``
        # separator — not on internal ``::``.
        m = re.match(r"\s*[-*]\s+(.+?)\s*:\s+(.+)$", line)
        if not m:
            continue
        tid = m.group(1).strip().strip("`")
        rest = m.group(2)
        # skip template placeholder rows like "<task_id>"
        if not tid or tid.startswith("<") or tid.startswith("#"):
            continue
        low = rest.lower()
        if "model-limited" in low or "model limited" in low or "unsolvable" in low:
            per_task[tid] = LIMITED
        elif _F2P_RE.search(rest):
            per_task[tid] = F2P
        elif _P2F_RE.search(rest):
            per_task[tid] = P2F
        elif "protect" in low or re.search(r"pass\s*(?:→|-+>?)\s*pass", rest, re.IGNORECASE):
            per_task[tid] = PROT

    return ParsedPrediction(base_raw=base_raw, base_iter=base_iter, per_task=per_task)


# --- per-task outcome helpers ------------------------------------------------

def load_task_outcomes(result_path: Path) -> dict[str, bool]:
    """Read a candidate_results/*.json and return ``{task_id: passed}``."""
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, bool] = {}
    for t in d.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = t.get("task_id") or t.get("id") or t.get("question_id")
        if tid is None:
            continue
        passed = t.get("passed")
        if passed is None:
            score = t.get("score")
            passed = score is not None and float(score) > 0
        out[str(tid)] = bool(passed)
    return out


def actual_flips(
    candidate_outcomes: dict[str, bool], base_outcomes: dict[str, bool]
) -> dict[str, str]:
    """Per-task flip of candidate vs base: F2P / P2F for tasks present in both."""
    flips: dict[str, str] = {}
    for tid, cand_pass in candidate_outcomes.items():
        if tid not in base_outcomes:
            continue
        base_pass = base_outcomes[tid]
        if base_pass and not cand_pass:
            flips[tid] = P2F
        elif (not base_pass) and cand_pass:
            flips[tid] = F2P
    return flips


def score_prediction(pred: ParsedPrediction, flips: dict[str, str]) -> dict:
    """Score the predicted per-task flips against the realized flips."""
    pred_f2p = {t for t, d in pred.per_task.items() if d == F2P}
    pred_p2f = {t for t, d in pred.per_task.items() if d == P2F}
    act_f2p = {t for t, d in flips.items() if d == F2P}
    act_p2f = {t for t, d in flips.items() if d == P2F}

    f2p_hits = pred_f2p & act_f2p
    p2f_hits = pred_p2f & act_p2f
    total_pred = len(pred_f2p) + len(pred_p2f)
    total_hits = len(f2p_hits) + len(p2f_hits)
    flip_hit_rate = (total_hits / total_pred) if total_pred else None

    blind = sorted(act_p2f - pred_p2f)  # regressions the proposer did NOT name
    false_flips = sorted((pred_f2p - act_f2p) | (pred_p2f - act_p2f))

    # Honest-ceiling: tasks declared model-limited (predicted to stay fail).
    # "Overruled" = called unsolvable but actually flipped to pass (pessimism).
    limited = {t for t, d in pred.per_task.items() if d == LIMITED}
    limited_overruled = sorted(limited & act_f2p)

    return {
        "flip_hit_rate": flip_hit_rate,
        "n_predicted_flips": total_pred,
        "n_flip_hits": total_hits,
        "predicted_fail_to_pass": sorted(pred_f2p),
        "predicted_pass_to_fail": sorted(pred_p2f),
        "actual_fail_to_pass": sorted(act_f2p),
        "actual_pass_to_fail": sorted(act_p2f),
        "blind_spot_regressions": blind,
        "n_blind_spot_regressions": len(blind),
        "false_flips": false_flips,
        "net_real_flips": len(act_f2p) - len(act_p2f),
        "model_limited": sorted(limited),
        "n_model_limited": len(limited),
        "model_limited_overruled": limited_overruled,
        "n_model_limited_overruled": len(limited_overruled),
        "base_raw": pred.base_raw,
        "base_iter": pred.base_iter,
    }


def evaluate_prediction(
    prediction_text: str,
    candidate_outcomes: dict[str, bool],
    base_outcomes: dict[str, bool],
) -> dict:
    """End-to-end: parse + per-task flips + score. Returns the metrics dict."""
    pred = parse_prediction(prediction_text)
    flips = actual_flips(candidate_outcomes, base_outcomes)
    metrics = score_prediction(pred, flips)
    metrics["per_task_flips"] = flips
    return metrics


# --- run-dir helpers (used by the optimizer; thin, side-effecting) -----------

def load_score_breakdown(result_path: Path) -> dict:
    """Read a candidate_results/*.json and return its ``score_breakdown``.

    Retained for callers that still read the per-category breakdown (e.g. the
    base-resolution helper); per-task grading uses ``load_task_outcomes``.
    """
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d.get("score_breakdown") or {}


if __name__ == "__main__":  # quick self-test
    sample_pred = """# iter_5 prediction
## Candidate (one line)
query-biased compression
## Base — builds on iter_2 stack
## Mechanism — keep query-relevant sentences
## Per-task effects — the falsifiable prediction
- LME::s::aaa: fail→pass — denser evidence surfaces the date
- LME::s::bbb: fail→pass — less truncation across sessions
- LME::s::ccc: pass→fail — short answers may lose the cue
- LME::s::ddd: pass→pass (protected) — untouched retrieval path
## Model-limited (honest ceiling)
- LME::s::fff: model-limited — needs multi-hop arithmetic the model cannot do
- LME::s::ggg: model-limited — fabricated entity the model never grounds
## Falsification
if aaa does not flip, the mechanism is wrong
"""
    base = {"LME::s::aaa": False, "LME::s::bbb": False, "LME::s::ccc": True,
            "LME::s::ddd": True, "LME::s::eee": True,
            "LME::s::fff": False, "LME::s::ggg": False}
    cand = {"LME::s::aaa": True,   # predicted F2P, hit
            "LME::s::bbb": False,  # predicted F2P, missed
            "LME::s::ccc": False,  # predicted P2F, hit
            "LME::s::ddd": True,   # protected, stayed
            "LME::s::eee": False,  # surprise regression (not named)
            "LME::s::fff": False,  # model-limited, stayed fail (correct)
            "LME::s::ggg": True}   # model-limited but flipped → OVERRULED
    out = evaluate_prediction(sample_pred, cand, base)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    assert out["base_iter"] == 2
    assert out["predicted_fail_to_pass"] == ["LME::s::aaa", "LME::s::bbb"]
    assert out["predicted_pass_to_fail"] == ["LME::s::ccc"]
    assert sorted(out["actual_fail_to_pass"]) == ["LME::s::aaa", "LME::s::ggg"]
    assert sorted(out["actual_pass_to_fail"]) == ["LME::s::ccc", "LME::s::eee"]
    assert out["flip_hit_rate"] == 2 / 3  # aaa(F2P) + ccc(P2F) hit; bbb missed
    assert out["blind_spot_regressions"] == ["LME::s::eee"]
    assert out["false_flips"] == ["LME::s::bbb"]
    assert out["net_real_flips"] == 2 - 2
    assert out["model_limited"] == ["LME::s::fff", "LME::s::ggg"]
    assert out["model_limited_overruled"] == ["LME::s::ggg"]
    print("\nself-test OK")
