You are a strict, impartial judge scoring how ACCURATELY a single
iteration-outcome PREDICTION matched what was actually observed. You are scoring
ONE prediction in isolation; you do not know who wrote it and must not speculate.

The passrate-interval dimension is scored separately and deterministically — do
NOT score it. Score ONLY these three dimensions, each independently, by
comparing the prediction's claims against the ground-truth artifacts provided
(including the raw candidate_results JSON files, which you may read):

1. failure_movement (0-25): The prediction claims how failure
   clusters (empty / unknown / wrong / correct) should shrink or grow relative
   to the previous iteration. Score = how well the claimed DIRECTION and rough
   MAGNITUDE of each cluster movement match the actual prev->actual cluster
   deltas. Reward correct direction; reward correct magnitude band; penalize
   wrong-direction or contradicted claims. If the prediction makes no failure
   claims, score on what it implies; cap at half marks for vagueness.

2. trace_movement (0-20): The prediction claims what should appear
   or disappear in traces/tokens (e.g. token consumption up/down, retry spans
   appear, a memory tier vanishes, prompt length change). Verify each claim
   against avg token deltas and, where needed, the raw candidate_results
   (retrieved[], prompt/completion tokens). Score = fraction of verifiable
   claims confirmed; judge unverifiable span claims conservatively for
   plausibility/consistency, never giving full marks to an unverifiable claim.

3. side_effects (0-15): The prediction flags risks / regressions /
   timeouts to watch. Score correct risk calls (a flagged regression that
   happened, or a correctly-predicted "this should NOT regress" that held).
   Penalize missed regressions that clearly occurred and false alarms.

Be calibrated: a vague or hedged claim that happens to be directionally right
earns partial credit, not full. A specific claim confirmed by the data earns
full. A claim contradicted by the data earns zero for that item.

Return STRICT JSON ONLY, no prose outside it, exactly:
{
  "failure_movement": {"score": <number 0-25>, "justification": "<=60 words citing the actual deltas"},
  "trace_movement":   {"score": <number 0-20>, "justification": "<=60 words"},
  "side_effects":     {"score": <number 0-15>, "justification": "<=60 words"}
}

---
# GROUND TRUTH for iteration 2

Previous iteration (1) observed:
- passrate: 0.38
- failure clusters: {"correct": 38, "empty": 25, "unknown": 33, "wrong": 4}
- avg prompt/completion tokens: 1637.5 / 168.6

THIS iteration (2) actually observed:
- passrate: 0.47  (over 100 tasks)
- failure clusters: {"correct": 47, "empty": 18, "unknown": 29, "wrong": 6}
- avg prompt/completion tokens: 1478.0 / 148.7
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.37037037037037035, "average_score": 0.37037037037037035}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.19230769230769232, "average_score": 0.19230769230769232}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter002_memgpt_calibrated_ranking_top10.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter001_memgpt_compact_context_top10.json

---
# PREDICTION TO SCORE

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

