# Calibration-value test (leave-one-out)

**Question:** does the accumulated `world_model_calibration.md` actually make
the proposer predict iteration outcomes *more accurately*?

For each observable iteration N we compare three predictions of the **same
fixed candidate** against the **same observed outcome**, scored by the **same
blind judge**:

| | calibration it sees | who wrote it |
|---|---|---|
| **A** (historical) | only iters `< N` | the original kimi proposer (already on disk) |
| **B** (counterfactual) | full final calibration **minus iter N's own section**, with iter N's outcome **numbers redacted** | a fresh kimi prediction-only re-run |
| **C** (zero-WMC baseline) | **empty** calibration — task-framing preamble only, **zero distill** | a fresh kimi prediction-only re-run |

The cleanest test is **C vs B**: both predict a candidate they did not design,
so the only variable is empty vs full calibration. C carries **no hindsight at
all** (A only sees the past; B's surviving distills still qualitatively
reference iter N). The **objective passrate dimension** is the one dimension B
cannot win through hindsight, since iter N's numbers are redacted — so a tie
there means the accumulated calibration content has no transferable predictive
value. **C vs A** adds A's candidate-design advantage, so it reads as the
confounded end-to-end gap.

## Pipeline

```bash
# 0. one-time: env with KIMI_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY
set -a && source .env && set +a

# 1. stage scratch workspaces + ground truth (deterministic, no LLM)
python scripts/calib_value_test/stage.py                 # default pilot iters 1,2,3,11,16

# 2. re-run the kimi proposer (prediction-only) for conditions B and C
#    [~8 min/iter, docker; --workers N runs N iters concurrently]
python scripts/calib_value_test/rerun_b.py --condition B --workers 4
python scripts/calib_value_test/rerun_b.py --condition C --workers 4

# 3. compute deterministic passrate sub-scores + emit blind judge inputs (A/B/C)
python scripts/calib_value_test/score.py --emit-inputs

# 4. (orchestrator) run ONE blind judge subagent per
#    out/iter_NNN/scorer_input_{A,B,C}.md, save its JSON to
#    out/iter_NNN/llm_score_{A,B,C}.json

# 5. aggregate -> composite 0-100, paired A-vs-B, REPORT.md
python scripts/calib_value_test/score.py --aggregate
```

## Scoring (composite 0–100)

| dimension | pts | how |
|---|---|---|
| passrate-Δ | 40 | **deterministic** (`score.py`): coverage 25 (actual ∈ predicted interval, else penalized by distance, 0 at 0.10 outside) + sharpness 15 (narrower correct interval scores higher; 0 if not covered) |
| failure-type movement | 25 | blind LLM judge vs prev→actual cluster deltas |
| trace movement | 20 | blind LLM judge vs token deltas + raw `candidate_results` |
| side-effects | 15 | blind LLM judge: correct regression/risk calls |

## Files

- `common.py` — calibration leave-one-out + **numeric** redaction, prediction
  interval parsing, failure-cluster computation.
- `stage.py` — builds scratch workspaces + `ground_truth.json` + pinned
  `candidate_fixed.md` + prediction-only prompt.
- `rerun_b.py` — faithful kimi/docker prediction-only re-run (mirrors
  `launch_wmc_default_nosummary.sh`).
- `score.py` — deterministic passrate score, blind judge inputs, aggregation.
- `out/iter_NNN/` — `prediction_{A,B}.md`, `ground_truth.json`,
  `calibration_B.md`, `passrate_score_{A,B}.json`, `scorer_input_{A,B}.md`,
  `llm_score_{A,B}.json`, plus the run-wide `REPORT.md` / `scores.json`.

## Caveats (read before interpreting)

- **Qualitative hindsight leak.** Only *numbers* are redacted from the LOO
  calibration. Surviving distills still reference the target iter qualitatively
  (e.g. *"the same failure mode as iter_003→iter_004"*), so part of any B gain
  reflects hindsight, not purely transferable world-model knowledge.
- **B did not design its candidate.** B predicts a candidate handed to it
  (mechanism text + diff digest); A predicted one it designed. This biases
  *against* B, so a positive Δ is conservative.
- **Same proposer model both sides** (kimi-k2.6, same docker sandbox) so the
  only intended variable is the calibration content.
