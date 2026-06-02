"""Stage the leave-one-out calibration-value test (deterministic, no LLM).

For each pilot iteration N this:
  1. reconstructs a scratch workspace = a copy of iter N's original proposer
     workspace, but with
       - world_model_calibration.md  -> LOO+redacted full-final calibration
       - prediction.md               -> deleted (condition A's answer hidden)
       - candidate_fixed.md          -> added (the pinned candidate spec)
       - prompt_B.md                 -> added (prediction-only user prompt)
  2. writes ground_truth_iterNNN.json (actual passrate, clusters, tokens,
     parsed condition-A interval) for the scorer + deterministic passrate score
  3. copies condition A's prediction.md to the outputs dir

Run:  python scripts/calib_value_test/stage.py [--run PATH] [--iters 1,2,3]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

SCRATCH_ROOT = c.REPO / "runs" / "_calib_value_test" / "scratch"
OUT_ROOT = Path(__file__).resolve().parent / "out"


def _extract_sections(prediction_md: str, headings: tuple[str, ...]) -> str:
    """Return the requested ``## <heading>`` sections from a prediction file."""
    lines = prediction_md.split("\n")
    keep: list[str] = []
    grabbing = False
    for ln in lines:
        if ln.startswith("## "):
            grabbing = any(ln.strip().lower().startswith(f"## {h.lower()}") for h in headings)
        if grabbing:
            keep.append(ln)
    return "\n".join(keep).strip()


def _build_candidate_fixed(run: Path, n: int) -> str:
    pred = (c.iter_dir(run, n) / "workspace" / "prediction.md").read_text()
    digest_path = c.iter_dir(run, n) / "diff_digest.md"
    digest = digest_path.read_text() if digest_path.exists() else "(diff_digest.md missing)"
    cand_mech = _extract_sections(pred, ("Candidate", "Mechanism"))
    return (
        f"# Fixed candidate for iteration {n}\n\n"
        "This candidate has ALREADY been decided and implemented. It is the\n"
        "exact change that was evaluated this iteration. Predict ITS outcome —\n"
        "do not design a different candidate.\n\n"
        f"{cand_mech}\n\n"
        "## Actual code change (diff digest)\n\n"
        f"{digest}\n"
    )


def _build_prediction_only_prompt(run: Path, n: int, populated: bool = True) -> str:
    orig = (c.iter_dir(run, n) / "agent" / "attempt_01" / "proposer" / "prompt.md").read_text()
    # Keep the assignment + available-files context; drop candidate-design and
    # pending_eval output instructions (## Edit Scope / ## Required output ...).
    cut = len(orig)
    for marker in ("## Edit Scope", "## Required output", "## Edit scope"):
        idx = orig.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    context = orig[:cut].rstrip()

    if populated:
        calib_state = (
            "In this run it is\n"
            "   PRE-POPULATED with accumulated world-model beliefs. Do NOT append a new\n"
            "   distill section and do NOT edit it."
        )
    else:
        calib_state = (
            "In this run it holds ONLY the\n"
            "   initial task-framing preamble — there is NO accumulated world-model\n"
            "   content yet, so ground your prediction purely in the evidence below.\n"
            "   Do NOT append a new distill section and do NOT edit it."
        )

    directive = f"""
---

# THIS INVOCATION IS PREDICTION-ONLY (WorldCalib calibration-value test)

The candidate for iteration {n} has ALREADY been decided and implemented; it is
FIXED and described in `./candidate_fixed.md`. Your ONLY job is to predict its
observable outcome as accurately as you can.

Do exactly this, then stop:

1. `cat ./world_model_calibration.md` and read it in full. {calib_state}
2. Analyze the evidence under `reference_iterations/` and `traces/` exactly as
   your skill's step 1 describes, to ground your prediction in real failure
   modes. (`./prev_prediction.md` is also available.)
3. `cat ./candidate_fixed.md` — this is the exact mechanism that was
   implemented and evaluated. Do NOT invent a different candidate.
4. Write `./prediction.md` for THIS fixed candidate, in the EXACT skill format:

   ```
   # iter_{n:03d} prediction
   ## Candidate
   ## Mechanism
   ## Outcome prediction
   - Train passrate Δ: [low, high]
   - Failure type movement: ...
   - Trace movement: ...
   - Side effects to watch: ...
   ## Falsification
   ...
   ```

HARD CONSTRAINTS: Do NOT edit any source under `source_snapshot/`. Do NOT write
`pending_eval.json`. Do NOT append to `world_model_calibration.md`. Stop
immediately after writing `./prediction.md`.
"""
    return context + "\n" + directive


def _materialize_condition(
    src_ws: Path, dst_ws: Path, calib_text: str, candidate_fixed: str,
    prompt_text: str, prompt_name: str,
) -> None:
    """Build one prediction-only scratch workspace: a faithful copy of iter N's
    original proposer workspace, with the calibration swapped, condition A's
    answer hidden, and the pinned candidate + prediction-only prompt added."""
    if dst_ws.exists():
        shutil.rmtree(dst_ws)
    dst_ws.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_ws, dst_ws, symlinks=True)
    (dst_ws / "world_model_calibration.md").write_text(calib_text)
    (dst_ws / "prediction.md").unlink(missing_ok=True)  # hide condition A's answer
    (dst_ws / "candidate_fixed.md").write_text(candidate_fixed)
    (dst_ws / prompt_name).write_text(prompt_text)


def stage_iter(run: Path, n: int) -> dict:
    src_ws = c.iter_dir(run, n) / "workspace"
    if not src_ws.is_dir():
        raise FileNotFoundError(src_ws)

    iter_scratch = SCRATCH_ROOT / f"iter_{n:03d}"
    dst_ws_b = iter_scratch / "workspace"      # condition B (LOO final calibration)
    dst_ws_c = iter_scratch / "workspace_C"    # condition C (empty calibration)
    out_dir = OUT_ROOT / f"iter_{n:03d}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ground truth (actual observed outcome of iter N's candidate).
    rp = c.result_path_for(run, n)
    outcome = c.outcome_from_results(rp)
    # Reference base = previous iteration's actual passrate (best-effort).
    prev_rp = c.result_path_for(run, n - 1) if n > 1 else None
    prev_passrate = c.outcome_from_results(prev_rp)["passrate"] if prev_rp else None
    cond_a_pred = (src_ws / "prediction.md").read_text()
    interval = c.parse_prediction_interval(cond_a_pred)

    target_passrate = outcome["passrate"]

    # --- calibration per condition
    full_calib = (run / "world_model_calibration.md").read_text()
    loo_calib = c.build_loo_calibration(full_calib, n, target_passrate)  # B
    empty_calib = c.build_empty_calibration(full_calib)                  # C

    candidate_fixed = _build_candidate_fixed(run, n)
    prompt_b = _build_prediction_only_prompt(run, n, populated=True)
    prompt_c = _build_prediction_only_prompt(run, n, populated=False)

    _materialize_condition(src_ws, dst_ws_b, loo_calib, candidate_fixed, prompt_b, "prompt_B.md")
    _materialize_condition(src_ws, dst_ws_c, empty_calib, candidate_fixed, prompt_c, "prompt_C.md")

    # --- outputs for scorer / record
    (out_dir / "prediction_A.md").write_text(cond_a_pred)
    (out_dir / "candidate_fixed.md").write_text(candidate_fixed)
    (out_dir / "calibration_B.md").write_text(loo_calib)
    (out_dir / "prompt_B.md").write_text(prompt_b)
    (out_dir / "calibration_C.md").write_text(empty_calib)
    (out_dir / "prompt_C.md").write_text(prompt_c)
    gt = {
        "iteration": n,
        "candidate_id": outcome["candidate_id"],
        "actual_passrate": target_passrate,
        "prev_actual_passrate": prev_passrate,
        "clusters": outcome["clusters"],
        "n_tasks": outcome["n_tasks"],
        "avg_prompt_tokens": outcome["avg_prompt_tokens"],
        "avg_completion_tokens": outcome["avg_completion_tokens"],
        "score_breakdown": outcome["score_breakdown"],
        "candidate_results_file": rp.name if rp else None,
        "condition_a_interval": {
            "delta": [interval.delta_low, interval.delta_high],
            "abs": [interval.abs_low, interval.abs_high],
            "base": interval.base,
            "raw_line": interval.raw_line,
        },
    }
    (out_dir / "ground_truth.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False))
    return {
        "iter": n,
        "scratch_ws_B": str(dst_ws_b),
        "scratch_ws_C": str(dst_ws_c),
        "actual_passrate": target_passrate,
        "a_interval_abs": [interval.abs_low, interval.abs_high],
        "calib_chars_B": len(loo_calib),
        "calib_chars_C": len(empty_calib),
        "calib_sections_dropped_self": f"## iter_{n:03d} →" not in loo_calib,
        "C_has_no_distill": "→ iter_" not in empty_calib,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(c.DEFAULT_RUN))
    ap.add_argument("--iters", default=",".join(str(i) for i in c.PILOT_ITERS))
    args = ap.parse_args()
    run = Path(args.run)
    iters = [int(x) for x in args.iters.split(",") if x.strip()]
    print(f"staging {len(iters)} iters from {run.name}")
    for n in iters:
        info = stage_iter(run, n)
        print(json.dumps(info, ensure_ascii=False))
    print(f"\nscratch workspaces: {SCRATCH_ROOT}")
    print(f"outputs:            {OUT_ROOT}")


if __name__ == "__main__":
    main()
