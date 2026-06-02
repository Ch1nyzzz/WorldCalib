# iter_002 prediction

## Candidate
memgpt_calibrated_ranking

## Mechanism
Two failure families from iter_001:
1. Cross-tier score miscalibration: summary gets 0.2+cosine (≈0.30), core gets 0.1+cosine (≈0.15), but archival/recall RRF maxes at ~0.03. This forces the top-2 retrieval slots to always be summary/core metadata, pushing answer-bearing archival/recall passages down or out of the 6000-char budget.
2. Empty predictions: 25 fails produced empty strings while consuming exactly 256 completion tokens, suggesting the model burns its budget on hidden reasoning/thinking tokens or verbose quoting before reaching FINAL ANSWER.

Fix: (a) remove fixed additive boosts from summary/core scores and normalize RRF to [0,1] so relevant docs from any tier can compete; (b) increase max_tokens to 512; (c) simplify the prompt to direct concise answering without quoting; (d) keep iter_001's compact formatting.

## Outcome prediction
- Train passrate Δ: [+0.06, +0.14] (from 0.38 to ~0.44-0.52)
- Failure type movement: "unknown" predictions where gold is in lower-ranked docs should shrink; empty predictions should shrink or disappear
- Trace movement: retrieved documents should show more archival/recall in top ranks; prompt_tokens may rise slightly from more included docs; completion_tokens should show fewer 256-token ceilings
- Side effects to watch: if summary docs occasionally contain gold (observed 4/100), normalizing their scores could demote them; if max_tokens increase causes timeout or doesn't fix empty outputs, the thinking-token theory is wrong

## Falsification
If passrate stays below 0.42, the mechanism is falsified: either score calibration doesn't improve ranking quality, or empty predictions are due to an API-level issue (thinking tokens) that token budget can't fix.
