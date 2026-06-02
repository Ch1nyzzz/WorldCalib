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
Four coordinated changes:
1. **Score calibration & ranking**: removes fixed +0.2/+0.1 additive boosts from summary/core scores, normalizes RRF scores to [0,1], and reorders hits by raw score (tier becomes tiebreaker only). This lets relevant archival/recall passages compete for top context slots instead of being locked behind summary/core metadata.
2. **Generation budget**: increases `max_tokens` from 256 to 512 and falls back to `reasoning_content` when final `content` is empty. This directly targets the 25 tasks that produced empty predictions while burning exactly 256 tokens.
3. **Prompt simplification**: strips the "quote the relevant part" instruction in favor of concise direct answering, reducing token burn in the output.
4. **Retained compaction**: keeps iter_001's per-hit truncation (max_hit_chars=1200) and compact archival/recall formatting so more documents fit in the 6000-char budget.

## Outcome prediction
- **Train passrate Δ**: [+0.12, +0.20] (from 0.38 to ~0.50–0.58)
- **Failure type movement**:
  - The "empty prediction" cluster (25 tasks, all consuming 256 completion tokens) should shrink dramatically — 10–18 of these should convert to correct answers via the doubled token budget, reasoning_content fallback, and concise prompt.
  - The "truncated context / low-ranked evidence" cluster should shrink — 3–8 additional tasks should pass because relevant archival/recall docs now surface in the top-2 slots instead of being pushed out by boosted summary/core metadata.
  - The "unknown" cluster may shrink slightly (2–4 conversions) as better evidence ordering and a less conservative prompt help the model extract answers it previously rejected.
- **Trace movement**:
  - Completion tokens should rise from a median near 150–256 to ~200–400 for previously empty tasks.
  - Retrieved documents actually included in the prompt should increase from ~3–4 to ~5–7 because archival/recall docs now rank higher and max_hit_chars truncation prevents any single doc from monopolizing the budget.
  - Empty-string predictions should drop from 25 to <5.
- **Side effects to watch**:
  - Removing tier priority could cause 0–3 regressions among stable-pass tasks if they relied on summary/core ranking to keep a specific passage in-context, though summary/core are usually low-information metadata.
  - The reasoning_content fallback may produce verbose, unformatted text that the judge scores partially; watch for predictions that contain the correct answer buried in reasoning chains but lack the "FINAL ANSWER:" delimiter.
  - Token consumption per task will increase because max_tokens doubled; average completion tokens may rise by ~50–100.

## Falsification
- If passrate stays below 0.45, the mechanism is falsified: either the model still cannot extract answers even with more tokens and better ranking, or the reasoning_content fallback and prompt simplification do not translate to judge-scorable predictions.
- If empty predictions remain >15, the token-budget / reasoning_content fix did not work as hypothesized.
- If regressions exceed 5, removing tier priority is actively harmful despite the score normalization.

