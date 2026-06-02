# Calibration-value test — does A predict more accurately than C?

Run: `longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607`

Two predictions of the **same fixed candidate**, scored against the **same observed outcome** by the **same blind judge** (same kimi-k2.6 model). The only intended difference is the world model the proposer had:

- **A** = the real WMC proposer at iter N. It had read the accumulated `world_model_calibration.md` (every distill from iters < N) and designed this candidate itself.
- **C** = a zero-WMC baseline. The same proposer given an **empty** calibration (task-framing preamble only, zero distill), predicting the same fixed candidate.

If the accumulated calibration helps the proposer foresee outcomes, A should predict **more accurately** than C — and the edge should grow as calibration fills up.

Composite 0-100 = passrate-Δ (40, deterministic) + failure-movement (25) + trace-movement (20) + side-effects (15). `pass` = the 0-40 passrate sub-score; `tot` = composite. **A−C > 0 means A predicted better.**

| iter | actual | A pass | A tot | C pass | C tot | A−C |
|---|---|---|---|---|---|---|
| 1 | 0.38 | 15.00 | **45.00** | 28.75 | **52.75** | -7.75 |
| 2 | 0.47 | 34.00 | **76.00** | 17.50 | **42.50** | 33.50 |
| 3 | 0.27 | 0.00 | **20.00** | 0.00 | **22.00** | -2.00 |
| 4 | 0.49 | 5.00 | **28.00** | 20.00 | **48.00** | -20.00 |
| 5 | 0.39 | 0.00 | **14.00** | 0.00 | **8.00** | 6.00 |
| 6 | 0.50 | 12.50 | **51.50** | 34.75 | **64.75** | -13.25 |
| 8 | 0.53 | 20.00 | **45.00** | 12.50 | **34.50** | 10.50 |
| 9 | 0.54 | 17.50 | **52.50** | 15.00 | **34.00** | 18.50 |
| 10 | 0.53 | 12.50 | **47.50** | 20.00 | **49.00** | -1.50 |
| 11 | 0.47 | 2.50 | **29.50** | 7.50 | **31.50** | -2.00 |
| 12 | 0.57 | 34.75 | **72.75** | 17.50 | **53.50** | 19.25 |
| 13 | 0.63 | 35.50 | **86.50** | 35.50 | **71.50** | 15.00 |
| 14 | 0.66 | 37.00 | **75.00** | 37.75 | **74.75** | 0.25 |
| 15 | 0.66 | 17.50 | **37.50** | 22.50 | **48.50** | -11.00 |
| 16 | 0.69 | 37.00 | **77.00** | 37.75 | **73.75** | 3.25 |
| 17 | 0.17 | 0.00 | **4.00** | 0.00 | **4.00** | 0.00 |
| 18 | 0.64 | 7.50 | **33.50** | 12.50 | **46.50** | -13.00 |
| 19 | 0.61 | 2.50 | **35.50** | 5.00 | **24.00** | 11.50 |
| 20 | 0.69 | 22.50 | **52.50** | 37.75 | **68.75** | -16.25 |
| 24 | 0.62 | 2.50 | **24.50** | 7.50 | **28.50** | -4.00 |
| 25 | 0.69 | 22.50 | **62.50** | 22.50 | **45.50** | 17.00 |
| 27 | 0.71 | 37.75 | **70.75** | 37.75 | **65.75** | 5.00 |
| 28 | 0.68 | 15.00 | **33.00** | 15.00 | **29.00** | 4.00 |
| 29 | 0.11 | 0.00 | **7.00** | 0.00 | **3.00** | 4.00 |

## Paired statistics (Δ = A − C, positive = A predicted better)

| dimension | mean Δ | sd | t = mean/sem | A win/loss/tie | (max) |
|---|---|---|---|---|---|
| composite | +2.38 | 12.5 | +0.93 | 13/10/1 | /100 |
| passrate (objective) | -2.25 | 8.7 | -1.27 | 4/12/8 | /40 |
| qualitative (fail+trace+side) | +4.62 | 6.9 | +3.26 | 18/5/1 | /60 |

Mean composite: A = 45.0, C = 42.7 (of 100).

## By calibration thickness — does A's edge grow as the world model fills up?

Calibration is append-only, so A's `world_model_calibration.md` grows every iter while C's stays empty. If the accumulated content carried predictive value, A−C should **rise** from the thin to the thick bucket.

| thickness | n | chars | A−C composite | A−C passrate | A−C qualitative |
|---|---|---|---|---|---|
| thin | 8 | 787–9281 | +3.2 | -3.1 | +6.2 |
| mid | 8 | 10566–21809 | +2.9 | -0.2 | +3.1 |
| thick | 8 | 23467–31387 | +1.0 | -3.5 | +4.5 |

Spearman(thickness, A−C composite gap) = **+0.061** — essentially no correlation: A's edge does **not** grow with calibration size. Spearman(thickness, A's absolute composite) = -0.050.

## Conclusion

**Does A predict more accurately than C? On the objective passrate dimension, no.** A−C passrate = mean -2.25 (t=-1.27, not significant, 4/12/8) — A is, if anything, slightly behind the zero-WMC baseline at predicting the next outcome's numbers. Reading the accumulated world model did not sharpen the proposer's quantitative forecasts.

A does hold a small, significant edge on the **qualitative** dimensions (A−C = mean +4.62 (t=+3.26, significant, 18/5/1)). But the by-thickness breakdown shows this edge **does not grow as calibration accumulates** (Spearman ≈ 0). That is the signature of a *constant* advantage — A designed the candidate and so understands its failure modes — not of value pulled from the growing calibration text.

Overall composite A−C = mean +2.38 (t=+0.93, not significant, 13/10/1): the end-to-end WMC proposer is marginally ahead, but that margin is flat in calibration size and absent on the one objective, design-independent dimension. **The accumulated `world_model_calibration.md` does not make the proposer predict iteration outcomes more accurately**; the WMC gain is consistent with the predict-then-execute discipline, not the file as a reusable knowledge base.

> Caveats. (1) Same model (kimi-k2.6), same fixed candidate; the intended variable is empty vs accumulated calibration. A additionally designed the candidate, which favours A on the qualitative dimensions. (2) The passrate dimension is deterministic; the qualitative dimensions are blind-judged and A's vs C's sub-scores come from different judging batches, so a constant batch offset is possible — but it cannot create the flat-in-thickness trend, which is the load-bearing result. (3) n=24, single run (LongMemEval-s), single proposer.
