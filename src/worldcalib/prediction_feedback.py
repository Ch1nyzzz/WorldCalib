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


# --- aggregate (subset-level) bet: the calib addon's machine-gradable unit ---

@dataclass
class AggregateBet:
    """The ``## Aggregate bet (machine)`` block of a calib ``prediction.md``.

    Unlike the legacy per-task flips (banned by the calib addon as
    below-noise-floor), this bets a SUBSET's aggregate behavior: the mean
    stable pass-rate delta on named tasks plus a run-wide stable-regression
    bound. Concrete, checkable, and de-noised by averaging.
    """

    subset: list[str]
    min_mean_delta: float | None
    max_stable_regressions: int | None


def historically_unstable_tasks(
    matrix_tasks: dict[str, dict[str, float]], min_transitions: int = 2
) -> set[str]:
    """Task_ids whose cross-iteration pass/fail history oscillates.

    ``matrix_tasks`` is the ``tasks`` object of a staged
    ``task_score_matrix.json``: ``{task_id: {"iter_000": score, ...}}``.
    A task is historically unstable when its pass/fail sequence (score > 0,
    columns in iteration order) changes direction at least ``min_transitions``
    times. One transition is a legitimate one-off improvement or regression;
    two or more means the task already flips back and forth across scaffolds,
    so a flip under the current candidate carries no attribution signal.
    """
    unstable: set[str] = set()
    for task_id, cols in matrix_tasks.items():
        if not isinstance(cols, dict):
            continue
        ordered: list[tuple[int, float]] = []
        for key, val in cols.items():
            m = re.match(r"iter_?0*(\d+)$", str(key))
            if m and isinstance(val, (int, float)):
                ordered.append((int(m.group(1)), float(val)))
        seq = [v > 0 for _, v in sorted(ordered)]
        transitions = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
        if transitions >= min_transitions:
            unstable.add(str(task_id))
    return unstable


def parse_aggregate_bet(text: str) -> AggregateBet | None:
    """Parse the ``## Aggregate bet (machine)`` section; None if absent/empty."""
    body = _section_body(text, "aggregate bet")
    if not body.strip():
        return None
    subset: list[str] = []
    min_delta: float | None = None
    max_regr: int | None = None
    for line in body.splitlines():
        m = re.match(
            r"\s*[-*]\s*(subset|min_mean_delta|max_stable_regressions)\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "subset":
            subset = [
                t.strip().strip("`")
                for t in val.split(",")
                if t.strip() and not t.strip().startswith("<")
            ]
        elif key == "min_mean_delta":
            fm = re.search(r"-?\d+(?:\.\d+)?", val)
            if fm:
                min_delta = float(fm.group(0))
        elif key == "max_stable_regressions":
            im = re.search(r"\d+", val)
            if im:
                max_regr = int(im.group(0))
    if not subset and min_delta is None and max_regr is None:
        return None
    return AggregateBet(
        subset=subset, min_mean_delta=min_delta, max_stable_regressions=max_regr
    )


def grade_aggregate_bet(
    bet: AggregateBet,
    candidate_outcomes: dict[str, bool],
    base_outcomes: dict[str, bool],
    history_unstable: set[str] | None = None,
) -> dict:
    """Grade an aggregate bet on STABLE outcomes only (``load_task_outcomes``).

    Subset tasks unstable in either side are excluded and reported; the
    regression bound is checked run-wide (all tasks shared by both sides).

    ``history_unstable`` (from :func:`historically_unstable_tasks` over the
    staged ``task_score_matrix.json``) names tasks whose pass/fail already
    oscillates across prior iterations. Their flips are reported but NOT
    counted against ``max_stable_regressions``: charging a known noise task
    to the candidate misattributes noise as harm (and has caused mechanisms
    that were behaviorally working to be abandoned).
    """
    history_unstable = history_unstable or set()
    graded = [t for t in bet.subset if t in candidate_outcomes and t in base_outcomes]
    excluded = sorted(set(bet.subset) - set(graded))
    base_rate = (
        sum(base_outcomes[t] for t in graded) / len(graded) if graded else None
    )
    cand_rate = (
        sum(candidate_outcomes[t] for t in graded) / len(graded) if graded else None
    )
    delta = (
        cand_rate - base_rate
        if cand_rate is not None and base_rate is not None
        else None
    )
    all_regressions = sorted(
        t
        for t in candidate_outcomes
        if t in base_outcomes and base_outcomes[t] and not candidate_outcomes[t]
    )
    noisy_regressions = sorted(t for t in all_regressions if t in history_unstable)
    regressions = sorted(t for t in all_regressions if t not in history_unstable)
    delta_held = (
        delta >= bet.min_mean_delta
        if (bet.min_mean_delta is not None and delta is not None)
        else None
    )
    regr_held = (
        len(regressions) <= bet.max_stable_regressions
        if bet.max_stable_regressions is not None
        else None
    )
    return {
        "subset": list(bet.subset),
        "subset_graded": graded,
        "subset_excluded_unstable": excluded,
        "base_mean_pass": base_rate,
        "candidate_mean_pass": cand_rate,
        "mean_delta": delta,
        "predicted_min_mean_delta": bet.min_mean_delta,
        "delta_held": delta_held,
        "stable_regressions": regressions,
        "n_stable_regressions": len(regressions),
        "history_unstable_regressions": noisy_regressions,
        "n_history_unstable_regressions": len(noisy_regressions),
        "predicted_max_stable_regressions": bet.max_stable_regressions,
        "regressions_held": regr_held,
    }


def render_aggregate_grade(iteration: int, m: dict) -> str:
    """Render grade metrics as the ``aggregate_grade.md`` the proposer reads."""

    def fmt(x: object) -> str:
        if x is None:
            return "n/a"
        return f"{x:.3f}" if isinstance(x, float) else str(x)

    def verdict(v: bool | None) -> str:
        return "n/a" if v is None else ("HELD" if v else "MISSED")

    return "\n".join(
        [
            f"# aggregate grade — iter_{iteration:03d} "
            "(mechanical; an instrument reading, not a veto)",
            "",
            f"verdict: subset-delta {verdict(m['delta_held'])} | "
            f"regressions {verdict(m['regressions_held'])}",
            "",
            f"- subset graded (stable in base AND candidate): "
            f"{len(m['subset_graded'])}/{len(m['subset'])}",
            f"- excluded as unstable: "
            f"{', '.join(m['subset_excluded_unstable']) or 'none'}",
            f"- subset stable pass-rate: base {fmt(m['base_mean_pass'])} -> "
            f"candidate {fmt(m['candidate_mean_pass'])} "
            f"(delta {fmt(m['mean_delta'])}; predicted >= "
            f"{fmt(m['predicted_min_mean_delta'])})",
            f"- run-wide stable regressions: {m['n_stable_regressions']} "
            f"(predicted <= {fmt(m['predicted_max_stable_regressions'])})",
            f"- regression task_ids: {', '.join(m['stable_regressions']) or 'none'}",
            f"- flips on historically-oscillating tasks (NOT counted against "
            f"the bound; cross-iter noise per task_score_matrix): "
            f"{', '.join(m.get('history_unstable_regressions') or []) or 'none'}",
            "",
            "Reconcile this with your own grade in the distill block: agreement",
            "raises trust in your reading; disagreement is evidence your reading",
            "of the environment is biased somewhere.",
            "",
        ]
    )


# --- per-task outcome helpers ------------------------------------------------

def _iter_task_rows(result_path: Path):
    """Yield ``(task_id, passed, score)`` for every row in a result's tasks[].

    With multi-run evaluation (``runs >= 2``) the same task_id appears once per
    run; callers aggregate.
    """
    try:
        d = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for t in d.get("tasks") or []:
        if not isinstance(t, dict):
            continue
        tid = t.get("task_id") or t.get("id") or t.get("question_id")
        if tid is None:
            continue
        score = t.get("score")
        passed = t.get("passed")
        if passed is None:
            passed = score is not None and float(score) > 0
        yield str(tid), bool(passed), (float(score) if score is not None else None)


def load_task_outcomes(result_path: Path) -> dict[str, bool]:
    """Read a candidate_results/*.json and return ``{task_id: passed}``.

    Only STABLE tasks are returned: with multi-run evaluation a task whose runs
    disagree (e.g. 1/2 passed) is noise, not signal — it is dropped here so the
    per-task flip grader never attributes a flip to it. Single-run results are
    unaffected (every task is trivially stable).
    """
    runs_by_task: dict[str, list[bool]] = {}
    for tid, passed, _ in _iter_task_rows(result_path):
        runs_by_task.setdefault(tid, []).append(passed)
    return {
        tid: runs[0]
        for tid, runs in runs_by_task.items()
        if all(r == runs[0] for r in runs)
    }


def load_task_pass_runs(result_path: Path) -> dict[str, list[bool]]:
    """Per-task pass outcome of every run: ``{task_id: [passed, ...]}``.

    The unstable tasks (mixed True/False) that :func:`load_task_outcomes`
    drops are visible here for callers that want to report them.
    """
    runs_by_task: dict[str, list[bool]] = {}
    for tid, passed, _ in _iter_task_rows(result_path):
        runs_by_task.setdefault(tid, []).append(passed)
    return runs_by_task


def load_task_scores(result_path: Path) -> dict[str, float]:
    """Mean score per task across runs: ``{task_id: mean_score}``."""
    scores_by_task: dict[str, list[float]] = {}
    for tid, _, score in _iter_task_rows(result_path):
        if score is not None:
            scores_by_task.setdefault(tid, []).append(score)
    return {tid: sum(s) / len(s) for tid, s in scores_by_task.items()}


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

    # aggregate (machine) bet: parse + grade
    agg_pred = sample_pred + """
## Aggregate bet (machine) — parsed and graded mechanically
- subset: LME::s::aaa, LME::s::bbb, LME::s::ddd
- min_mean_delta: 0.30
- max_stable_regressions: 1
"""
    bet = parse_aggregate_bet(agg_pred)
    assert bet is not None
    assert bet.subset == ["LME::s::aaa", "LME::s::bbb", "LME::s::ddd"]
    assert bet.min_mean_delta == 0.30
    assert bet.max_stable_regressions == 1
    agg = grade_aggregate_bet(bet, cand, base)
    # subset: aaa F->T, bbb F->F, ddd T->T => base 1/3, cand 2/3, delta +1/3
    assert abs(agg["mean_delta"] - (2 / 3 - 1 / 3)) < 1e-9
    assert agg["delta_held"] is True
    # run-wide stable regressions: ccc, eee => 2 > 1 predicted
    assert agg["stable_regressions"] == ["LME::s::ccc", "LME::s::eee"]
    assert agg["regressions_held"] is False
    assert parse_aggregate_bet(sample_pred) is None  # no machine block

    # cross-iteration noise filter: a task that already oscillates across
    # prior iters must not be charged against the regression bound.
    matrix_tasks = {
        "LME::s::ccc": {"iter_000": 1.0, "iter_001": 1.0, "iter_002": 1.0},
        "LME::s::eee": {"iter_000": 1.0, "iter_001": 0.0, "iter_002": 1.0},
    }
    assert historically_unstable_tasks(matrix_tasks) == {"LME::s::eee"}
    agg2 = grade_aggregate_bet(bet, cand, base, history_unstable={"LME::s::eee"})
    assert agg2["stable_regressions"] == ["LME::s::ccc"]
    assert agg2["history_unstable_regressions"] == ["LME::s::eee"]
    assert agg2["regressions_held"] is True  # 1 counted <= 1 predicted
    print(render_aggregate_grade(5, agg))
    print("\nself-test OK")
