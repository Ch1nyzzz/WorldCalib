# World-Model Calibration (WMC) for Agent-System Optimization

**Authors**: Yuhan Chen (Ch1nyzzz) · **Last updated**: 2026-06-10
**Repos**: with-WMC = `WorldCalib`, no-WMC control = `Optimizer1`

---

## 1. Research question

> **Can we get a better candidate by calibrating the proposer's world model from past feedback?**
>
> Feedback → world-model calibration file → promote the proposer's world-model understanding to the target agent system by in-context learning.

The proposer is an LLM agent that iteratively rewrites the target agent system's source (a memory scaffold over a fixed target model). The hypothesis: forcing the proposer to **bet before it acts** — write down what the candidate will improve and what it will regress — and then **calibrate against the real rollout feedback** builds an increasingly accurate world model of the (benchmark × target-model × scaffold) system, which compounds into better candidates.

## 2. The two arms

### 2.1 no-WMC (control, in `Optimizer1`)

The standard proposer loop. Each iteration the proposer reads the score table, diffs, and failure traces of prior candidates, designs one mechanism-level change, and emits `pending_eval.json`. The outer loop evaluates the candidate on the train split. **No prediction is written, no calibration file exists** — the only cross-iteration memory is the raw evidence (scores, traces, diffs).

### 2.2 with-WMC, a.k.a. "calib" (treatment, in `WorldCalib`)

Identical loop **plus two files and one protocol** (predict-then-execute):

| File | Cadence | Content |
|---|---|---|
| `prediction.md` | per iter, written **before** editing source | The bet: **possible improvements and possible regressions** — which tasks this patch should save, and what regressions it may cause, each tied to trace evidence |
| `world_model_calibration.md` | per run, **append-only** | Each iter starts by comparing the previous `prediction.md` against the real evaluated outcome and appending one `## iter_N -> iter_N+1 distill` section: which calls were right/wrong, blind-spot regressions, and a one-line belief update |

Per-iteration pipeline (iter *n*):

1. **Self-distill**: read `prev_prediction.md` + the real per-task results of iter *n−1*; grade the bet; append the distill section to `world_model_calibration.md`.
2. **Propose + predict**: design one change; write `prediction.md` (upsides: which tasks flip fail→pass; downsides: which tasks are at risk of pass→fail; which failures are model-limited).
3. **Rollout & evaluate**: outer loop runs the candidate on the train split, records per-task outcomes and traces.
4. Loop. The accumulated `world_model_calibration.md` is staged into every future iteration's workspace — **the world model is promoted to the next proposer call purely by in-context learning**.

Design constraints: append-only (mistakes must be distilled, not deleted); no separate reward model or shadow gate; only falsifiable outcome predictions allowed (no vague "generalization judgements").

## 3. End-to-end results: with-WMC vs no-WMC

Setup (matched across arms): proposer = Claude Kimi K2.6 max-effort; target = DeepSeek v4 Flash; seed scaffold = `memgpt_source top12`; 30 iterations; LongMemEval-s train = 100 questions, LoCoMo train = 80 questions. iter_0 baselines: LME 0.16, LoCoMo 0.287.

### 3.1 Train passrate

| Benchmark | no-WMC best | with-WMC best | Δ abs | Δ rel |
|---|---:|---:|---:|---:|
| LongMemEval-s | 0.59 @ iter_30 | **0.71** @ iter_27 | +0.12 | **+20.3%** |
| LoCoMo | 0.4125 @ iter_08 | **0.475** @ iter_17 | +0.063 | **+15.3%** |

### 3.2 Held-out test passrate (top-1 of train quality frontier, re-evaluated)

| Benchmark | Test size | no-WMC top-1 | with-WMC top-1 | Δ |
|---|---:|---:|---:|---:|
| LongMemEval-s | 400 | 0.5325 (`adaptive_recovery_temporal_facet`) | **0.6075** (`adjacent_archival_merge_1536`) | **+0.075 (+14.1%)** |
| LoCoMo | 1449 | 0.3692 (`temporal_aligned_retrieval`) | **0.4534** (`context_expansion_with_compression`) | **+0.084 (+22.7%)** |

On LoCoMo the test-time relative gain (+22.7%) exceeds the train gain (+15.3%): the WMC-found scaffold generalizes better, it is not just train-fit.

### 3.3 Speed-to-threshold (LongMemEval-s)

| Threshold | no-WMC first reach | with-WMC first reach |
|---:|---:|---:|
| 0.30 | iter_05 | iter_01 (5×) |
| 0.49 | iter_15 | iter_04 (3.75×) |
| 0.55 | iter_23 | iter_12 |
| 0.60 / 0.70 | never | iter_13 / iter_27 |

On LoCoMo the control hit the 0.412 ceiling five times (iters 8/13/16/21/23) and never broke it; WMC broke through to 0.45 at iter_10 and pushed to 0.475.

### 3.4 Cost

WMC is also **cheaper**: proposer cost dropped 22–25% (LME $102.81 → $77.08; LoCoMo $120.81 → $93.88). The append-only calibration file is a stable prompt prefix (cache hit ↑) and a ready-made global distill (proposer Read calls ↓ 28–40%).

### Run pointers

- no-WMC: `Optimizer1/runs/{longmemeval_s,locomo}_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_iter30_20260526_224520`
- with-WMC: `WorldCalib/runs/longmemeval_s_..._default_nosummary_wmc_iter30_20260527_212607`, `WorldCalib/runs/locomo_..._wmc_iter30_20260528_001003`
- Full report: `WorldCalib/REPORT.md`

## 4. But is the proposer's *prediction* getting more precise?

This is the catch the ablations surfaced: **WMC reliably yields better candidates, but the online prediction accuracy does not visibly improve over iterations.** Two findings refine the picture:

### 4.1 The world model *is* informative (offline pairwise blind judge)

`scripts/posthoc_calib_predict.py`: for a fixed candidate, two **fresh** predictors (neither designed the candidate) predict the same outcome under the same protocol; the only variable is whether they read the run's final `world_model_calibration.md` (leave-one-out: the candidate's own distill removed). A blind judge sees both anonymized predictions plus the mechanically computed ground truth and picks the more accurate one.

| Run | WM blind-judge win rate | downside_recall (no-WM → WM) |
|---|---|---|
| WMC LME | **10 / 10** | 0.0 → **1.0** |
| WMC LoCoMo | **9 / 10** | — (no sizable regressions in batch) |
| calib LME | **8 / 10** | 0.29 → 0.50 |
| calib LoCoMo | **9 / 10** | 0.57 → 0.71 |
| **Total** | **36 / 40 = 90%** | consistently ↑ |

The advantage concentrates almost entirely in **regression anticipation**: a predictor without the world model is naively optimistic and misses real regressions; with the accumulated world model it names which question types will degrade. (Details: `WorldCalib/ABLATION_calibration_value.md`.)

### 4.2 Why online precision still doesn't improve

The original protocol asked for **scalar/per-bucket score deltas**, which turned out to be near-random and fed the optimizer's curse (the proposer learns to promise big numbers, not to be right). We have since redesigned the prediction to be **per-task and falsifiable**: name the concrete `task_id`s the patch flips fail→pass, the at-risk tasks that may flip pass→fail, and the honestly **model-limited** tasks no harness change can save. The prediction may name tasks; the code must stay general (never branch on a task_id).

## 5. Next step: put the prediction score *inside* the optimization objective

Current calib runs are **self-distill**: the proposer grades its own previous bet, with no external check. The proposed extension:

> **Iter *n***: proposer emits candidate + `prediction.md` (scores, upsides, potential downsides) → rollout & evaluate traces → **a Critic judges the gap between `prediction.md` and the true feedback** and writes `critic_feedback.md` → **iter *n+1* the proposer must jointly optimize the pass rate *and* narrow the prediction gap.**

This makes calibration error a first-class optimization signal rather than a self-graded diary, directly attacking §4's gap.

**Pilot caveat (already observed)**: a critic-in-the-loop pilot on LME showed the critic must be a *calibrator*, not a *gatekeeper*. When the critic could veto candidates broadly, the search froze (best 0.40–0.49 across three pilot runs); restricting the veto to a narrow block-list (per-task-type overfitting / reward hacking → revise) recovered the search to 0.63. The critic should score the prediction–feedback gap and feed it back as pressure, not hard-filter the search space.

## 6. Takeaways

1. **WMC works end-to-end**: +12–20% train, +14–23% held-out test, faster breakthroughs, 22–25% cheaper proposer — on both LongMemEval-s and LoCoMo.
2. **The accumulated world model carries real, reusable knowledge** (36/40 blind-judge wins), concentrated in predicting regressions.
3. **Online prediction precision is the open problem**: scalar score bets were noise; per-task flip predictions + a gap-scoring (not gatekeeping) Critic are the path to making prediction accuracy itself improve over the run.
