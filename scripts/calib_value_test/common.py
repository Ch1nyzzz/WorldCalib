"""Shared helpers for the calibration-value (leave-one-out) test.

The experiment asks: does the accumulated ``world_model_calibration.md``
actually make the proposer predict iteration outcomes more accurately?

For each observable iteration N we compare two predictions of the SAME
candidate against the SAME observed outcome:

* condition A (historical baseline) — the ``prediction.md`` the kimi proposer
  actually wrote at iter N, whose calibration only held iters < N.
* condition B (counterfactual) — a fresh kimi prediction of the same fixed
  candidate, given the full final calibration MINUS iter N's own section and
  with iter N's outcome numbers redacted from every remaining section.

This module holds the pieces both ``stage.py`` and ``score.py`` need:
calibration leave-one-out + redaction, prediction-interval parsing, and
failure-cluster computation from ``candidate_results``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUN = (
    REPO
    / "runs"
    / "longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607"
)
PILOT_ITERS = (1, 2, 3, 11, 16)


def iter_dir(run: Path, n: int) -> Path:
    return run / "proposer_calls" / f"iter_{n:03d}"


# ---------------------------------------------------------------------------
# Calibration leave-one-out + redaction
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^## iter_(\d+) → iter_(\d+) distill", re.MULTILINE)
_ITER_TOKEN_RE = re.compile(r"iter_(\d+)")
# A passrate-like decimal: 0.69, .69, +0.03, -0.10, 0.3625
_DECIMAL_RE = re.compile(r"[+-]?\d*\.\d+")


def _split_sections(text: str) -> list[str]:
    """Split calibration into the preamble + one chunk per ``## iter_..`` head."""
    heads = list(_SECTION_RE.finditer(text))
    if not heads:
        return [text]
    chunks = [text[: heads[0].start()]]  # preamble
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        chunks.append(text[m.start() : end])
    return chunks


def _redact_target_numbers(line: str, target: int, target_passrate: float | None) -> str:
    """If a line mentions iter ``target``, blank out the target's passrate value.

    Future distill sections cite the target iter's actual passrate as a
    baseline (e.g. ``vs iter_016's 0.69``). That decimal is exactly the
    quantity we score, so it must not leak into condition B. We redact only
    decimals equal to the target's passrate, on lines that name the target
    iter — this kills the leaked number while preserving the other iters'
    own outcome figures (which are legitimate world-model signal) and every
    qualitative belief.
    """
    iters = {int(t) for t in _ITER_TOKEN_RE.findall(line)}
    if target not in iters:
        return line
    if target_passrate is None:
        return _DECIMAL_RE.sub("<redacted>", line)  # conservative fallback

    def _sub(m: re.Match) -> str:
        try:
            val = float(m.group(0))
        except ValueError:
            return m.group(0)
        return "<redacted>" if abs(abs(val) - target_passrate) <= 0.005 else m.group(0)

    return _DECIMAL_RE.sub(_sub, line)


def build_loo_calibration(
    full_calib: str, target: int, target_passrate: float | None = None
) -> str:
    """Full final calibration MINUS iter ``target``'s own section, with the
    target iter's outcome numbers redacted from every surviving section."""
    out_chunks: list[str] = []
    for chunk in _split_sections(full_calib):
        m = _SECTION_RE.match(chunk)
        if m and int(m.group(1)) == target:
            # Drop iter N's own "iter_N → iter_(N+1)" distill outright: its
            # "Outcome mismatch" line literally states iter N's result.
            continue
        scrubbed = "\n".join(
            _redact_target_numbers(ln, target, target_passrate)
            for ln in chunk.split("\n")
        )
        out_chunks.append(scrubbed)
    return "".join(out_chunks)


def build_empty_calibration(full_calib: str) -> str:
    """Condition C's calibration: the task-framing preamble ONLY, with zero
    accumulated distill knowledge.

    This is exactly what the proposer saw before iteration 1 ran — the
    observability framing and the "predict outcomes, not generalization"
    instruction are present (so C is held to the same task contract as A/B),
    but no world-model content exists yet. It is identical for every iter and
    carries no hindsight whatsoever, which makes C the clean "never saw any
    WMC content" baseline that A (sees iters < N) and B (sees the LOO final)
    are both measured against.
    """
    return _split_sections(full_calib)[0]


# ---------------------------------------------------------------------------
# Prediction parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PredInterval:
    delta_low: float | None
    delta_high: float | None
    abs_low: float | None
    abs_high: float | None
    base: float | None
    raw_line: str


# matches: "Train passrate Δ: [+0.06, +0.12] (from 0.47 to ~0.53–0.59)"
# the absolute clause is optional and uses either - or – as the range dash.
# Tolerate markdown emphasis between Δ and ':' (e.g. "**...Δ**:").
_DELTA_LINE_RE = re.compile(r"passrate\s*Δ\s*\**\s*:\s*\[([^\]]+)\]([^\n]*)", re.IGNORECASE)
# The absolute-passrate prediction is an "A–B" decimal range in the trailing
# clause (after the delta bracket). It is often introduced by a tilde
# ("to ~0.53–0.59") but the proposer sometimes writes it plainly
# ("expected 0.26–0.41", "new passrate 0.70–0.73"), so the tilde is optional.
# Since the delta interval lives inside [...] (already consumed as group 1),
# the first decimal range in the trailing clause is the absolute prediction.
_ABS_RE = re.compile(r"~?\s*([+-]?\d*\.\d+)\s*[–\-]\s*([+-]?\d*\.\d+)")
_FROM_RE = re.compile(r"(?:from|baseline of|of)\s*([+-]?\d*\.\d+)")


def parse_prediction_interval(prediction_md: str) -> PredInterval:
    m = _DELTA_LINE_RE.search(prediction_md)
    if not m:
        return PredInterval(None, None, None, None, None, "")
    raw_line = m.group(0).strip()
    inside, rest = m.group(1), m.group(2)
    nums = _DECIMAL_RE.findall(inside)
    dlo = float(nums[0]) if len(nums) >= 1 else None
    dhi = float(nums[1]) if len(nums) >= 2 else None
    base = None
    fm = _FROM_RE.search(rest)
    if fm:
        base = float(fm.group(1))
    abs_lo = abs_hi = None
    am = _ABS_RE.search(rest)
    if am:
        abs_lo, abs_hi = float(am.group(1)), float(am.group(2))
    elif base is not None and dlo is not None and dhi is not None:
        abs_lo, abs_hi = base + dlo, base + dhi
    return PredInterval(dlo, dhi, abs_lo, abs_hi, base, raw_line)


# ---------------------------------------------------------------------------
# Ground-truth outcome from candidate_results / eval_summary
# ---------------------------------------------------------------------------

_UNKNOWN_RE = re.compile(r"\b(unknown|i don'?t know|cannot|can't|no (info|answer)|not (sure|enough))\b", re.IGNORECASE)


def classify_task(task: dict) -> str:
    pred = str(task.get("prediction") or "").strip()
    if task.get("passed"):
        return "correct"
    if pred == "":
        return "empty"
    if _UNKNOWN_RE.search(pred):
        return "unknown"
    return "wrong"


def outcome_from_results(results_path: Path) -> dict:
    d = json.loads(results_path.read_text())
    tasks = d.get("tasks", [])
    clusters = {"correct": 0, "empty": 0, "unknown": 0, "wrong": 0}
    ptok = ctok = 0
    n = len(tasks) or 1
    for t in tasks:
        clusters[classify_task(t)] += 1
        ptok += int(t.get("prompt_tokens") or 0)
        ctok += int(t.get("completion_tokens") or 0)
    return {
        "n_tasks": len(tasks),
        "passrate": round(clusters["correct"] / n, 4),
        "clusters": clusters,
        "avg_prompt_tokens": round(ptok / n, 1),
        "avg_completion_tokens": round(ctok / n, 1),
        "score_breakdown": d.get("score_breakdown", {}),
        "candidate_id": d.get("candidate", {}).get("candidate_id")
        if isinstance(d.get("candidate"), dict)
        else None,
    }


def eval_passrate(eval_summary_path: Path) -> float | None:
    d = json.loads(eval_summary_path.read_text())
    cands = d.get("candidates") or []
    if not cands:
        return None
    return float(cands[0].get("passrate"))


def result_path_for(run: Path, n: int) -> Path | None:
    """Locate candidate_results/iterNNN_*.json for an iteration."""
    hits = sorted((run / "candidate_results").glob(f"iter{n:03d}_*.json"))
    return hits[0] if hits else None
