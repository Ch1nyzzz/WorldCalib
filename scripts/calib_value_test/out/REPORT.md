# Calibration-value test — A vs B vs C

Run: `longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607`

Three predictions of the **same fixed candidate**, scored against the **same observed outcome** by the **same blind judge**:

- **A** = historical prediction; its calibration held only iters < N, and it designed the candidate itself (looks only at the past, no hindsight).
- **B** = fresh kimi prediction given the full final calibration minus iter N's own section (numbers redacted). Carries qualitative **future hindsight** and did not design the candidate.
- **C** = fresh kimi prediction given an **empty** calibration (task-framing preamble only, zero distill). The clean **zero-WMC** baseline — no accumulated world model at all, no hindsight, did not design the candidate.

Composite 0-100 = passrate-Δ (40, deterministic) + failure-movement (25) + trace-movement (20) + side-effects (15). `pass` column = the 0-40 passrate sub-score; `tot` = composite.

| iter | actual | A pass | A tot | B pass | B tot | C pass | C tot | C−A | C−B |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.38 | 15.00 | **45.00** | 15.00 | **33.00** | 28.75 | **52.75** | 7.75 | 19.75 |
| 2 | 0.47 | 34.00 | **76.00** | 37.00 | **71.00** | 17.50 | **42.50** | -33.50 | -28.50 |
| 3 | 0.27 | 0.00 | **20.00** | 0.00 | **23.00** | 0.00 | **22.00** | 2.00 | -1.00 |
| 4 | 0.49 | 5.00 | **28.00** | 37.00 | **71.00** | 20.00 | **48.00** | 20.00 | -23.00 |
| 5 | 0.39 | 0.00 | **14.00** | 0.00 | **20.00** | 0.00 | **8.00** | -6.00 | -12.00 |
| 6 | 0.50 | 12.50 | **51.50** | 2.50 | **27.50** | 34.75 | **64.75** | 13.25 | 37.25 |
| 8 | 0.53 | 20.00 | **45.00** | 36.25 | **74.25** | 12.50 | **34.50** | -10.50 | -39.75 |
| 9 | 0.54 | 17.50 | **52.50** | 17.50 | **50.50** | 15.00 | **34.00** | -18.50 | -16.50 |
| 10 | 0.53 | 12.50 | **47.50** | 20.00 | **51.00** | 20.00 | **49.00** | 1.50 | -2.00 |
| 11 | 0.47 | 2.50 | **29.50** | 7.50 | **30.50** | 7.50 | **31.50** | 2.00 | 1.00 |
| 12 | 0.57 | 34.75 | **72.75** | 17.50 | **61.50** | 17.50 | **53.50** | -19.25 | -8.00 |
| 13 | 0.63 | 35.50 | **86.50** | 35.50 | **87.50** | 35.50 | **71.50** | -15.00 | -16.00 |
| 14 | 0.66 | 37.00 | **75.00** | 37.00 | **69.00** | 37.75 | **74.75** | -0.25 | 5.75 |
| 15 | 0.66 | 17.50 | **37.50** | 37.75 | **65.75** | 22.50 | **48.50** | 11.00 | -17.25 |
| 16 | 0.69 | 37.00 | **77.00** | 37.75 | **73.75** | 37.75 | **73.75** | -3.25 | 0.00 |
| 17 | 0.17 | 0.00 | **4.00** | 0.00 | **23.00** | 0.00 | **4.00** | 0.00 | -19.00 |
| 18 | 0.64 | 7.50 | **33.50** | 17.50 | **52.50** | 12.50 | **46.50** | 13.00 | -6.00 |
| 19 | 0.61 | 2.50 | **35.50** | 2.50 | **29.50** | 5.00 | **24.00** | -11.50 | -5.50 |
| 20 | 0.69 | 22.50 | **52.50** | 22.50 | **46.50** | 37.75 | **68.75** | 16.25 | 22.25 |
| 24 | 0.62 | 2.50 | **24.50** | 5.00 | **45.00** | 7.50 | **28.50** | 4.00 | -16.50 |
| 25 | 0.69 | 22.50 | **62.50** | 37.75 | **51.75** | 22.50 | **45.50** | -17.00 | -6.25 |
| 27 | 0.71 | 37.75 | **70.75** | 37.75 | **72.75** | 37.75 | **65.75** | -5.00 | -7.00 |
| 28 | 0.68 | 15.00 | **33.00** | 15.00 | **32.00** | 15.00 | **29.00** | -4.00 | -3.00 |
| 29 | 0.11 | 0.00 | **7.00** | 0.00 | **2.00** | 0.00 | **3.00** | -4.00 | 1.00 |

## Paired statistics (Δ = first − second)

| comparison | dimension | mean Δ | sd | t = mean/sem | hi win/loss/tie | (max) |
|---|---|---|---|---|---|---|
| B−A | composite | +3.47 | 15.2 | +1.12 | 12/12/0 | /100 |
| B−A | passrate (objective) | +3.55 | 9.6 | +1.81 | 10/2/12 | /40 |
| B−A | qualitative (fail+trace+side) | -0.08 | 10.1 | -0.04 | 11/13/0 | /60 |
| C−A | composite | -2.38 | 12.5 | -0.93 | 10/13/1 | /100 |
| C−A | passrate (objective) | +2.25 | 8.7 | +1.27 | 12/4/8 | /40 |
| C−A | qualitative (fail+trace+side) | -4.62 | 6.9 | -3.26 | 5/18/1 | /60 |
| C−B | composite | -5.84 | 16.1 | -1.77 | 6/17/1 | /100 |
| C−B | passrate (objective) | -1.30 | 11.5 | -0.56 | 6/7/11 | /40 |
| C−B | qualitative (fail+trace+side) | -4.54 | 8.2 | -2.72 | 7/16/1 | /60 |

Mean composite: A = 45.0, B = 48.5, C = 42.7 (of 100).

## Conclusion

**The clean isolation of calibration *content* is C vs B** — both arms predict a candidate they did not design, so the only variable is empty vs full calibration. On the **objective passrate dimension**, the one dimension B's number-redacted calibration cannot telegraph, the two arms are statistically tied (mean -1.30 (t=-0.56, not significant, 6/7/11)). Loading the accumulated world model does **not** make the proposer predict the next outcome's numbers measurably better than a blank-slate proposer. B's only edge over C is in the **qualitative** dimensions (mean -4.54 (t=-2.72, significant, 7/16/1)) — precisely where B's surviving future-distill text describes the iter's failure modes. That is **hindsight, not transferable world-model skill**.

**C vs A** (zero-WMC vs the real historical proposer, which additionally saw only the past AND designed its own candidate). On the objective passrate dimension the zero-WMC arm is actually no worse — mean +2.25 (t=+1.27, not significant, 12/4/8) — and only trails on the composite (mean -2.38 (t=-0.93, not significant, 10/13/1)) via the qualitative dimensions (mean -4.62 (t=-3.26, significant, 5/18/1)), which A wins largely because it designed its own candidate and understands its failure modes. Read C vs A as the confounded end-to-end gap, not a clean calibration-content effect.

**Bottom line.** Across both clean views — C vs B (content isolation) and the objective passrate dimension of C vs A — the accumulated `world_model_calibration.md` shows **no transferable predictive value**: a blank-slate proposer predicts iteration outcomes about as accurately. This is consistent with the end-to-end WMC gain coming from the **predict-then-execute discipline itself**, not from the calibration file functioning as a reusable knowledge base.

For reference the original two-arm result is preserved as **B vs A**: composite mean +3.47 (t=+1.12, not significant, 12/12/0), passrate mean +3.55 (t=+1.81, marginal, 10/2/12).

> Caveats. (1) B (not C) carries qualitative future hindsight: only numbers were redacted from its LOO calibration. C carries none — it is the cleanest arm. (2) Both B and C predict a candidate they did not design, which biases them against A. (3) The A/B qualitative sub-scores come from the original judging batch; C's come from a fresh batch with the same rubric — so cross-arm qualitative deltas may carry minor judge-batch variance. The objective passrate dimension is deterministic and fully comparable across all three arms. (4) n=24, single run (LongMemEval-s), single proposer (kimi-k2.6).
