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
# GROUND TRUTH for iteration 13

Previous iteration (12) observed:
- passrate: 0.57
- failure clusters: {"correct": 57, "empty": 2, "unknown": 33, "wrong": 8}
- avg prompt/completion tokens: 1460.7 / 233.4

THIS iteration (13) actually observed:
- passrate: 0.63  (over 100 tasks)
- failure clusters: {"correct": 63, "empty": 3, "unknown": 25, "wrong": 9}
- avg prompt/completion tokens: 1651.5 / 208.1
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.48148148148148145, "average_score": 0.48148148148148145}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.9411764705882353, "average_score": 0.9411764705882353}, "temporal-reasoning": {"count": 26, "passrate": 0.5384615384615384, "average_score": 0.5384615384615384}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter013_multi_granularity_adaptive_retrieval_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter012_answer_signal_prioritized_two_tier_context_top8.json

---
# PREDICTION TO SCORE

# iter_013 prediction

## Candidate
multi_granularity_adaptive_retrieval

## Mechanism
The dominant failure family is retrieval misses: 31 of 43 failures in iter_012 have the gold answer string absent from all retrieved hits. Evidence source 1: task 1a1907b4 (cocktail suggestions) retrieves 12 docs about scented sprays and lens purchases; the mixology-class doc is missing. Evidence source 2: task 129d1232 (total charity raised) retrieves cycling tips and waste reduction; the docs with additional fundraising amounts are missing. Evidence source 3: task 10d9b85a (April workshop days) retrieves joke questions and theatre reviews; the April attendance doc is missing.

The new mechanism is multi-granularity archival indexing paired with adaptive retrieval limits:
1. **Turn-level archival passages** (chunk_size=1) are indexed alongside the original chunk passages. This reduces relevance dilution: a relevant turn is no longer penalized for sharing a chunk with irrelevant neighbors, so it can rank higher in sparse retrieval.
2. **Four-pass retrieval** runs BM25+cosine on both chunk and turn indexes with both the full query and a keyword-only (stopword-removed) query, then fuses the four rankings with RRF. This increases the chance that a relevant doc surfaces.
3. **Adaptive retrieval limits** scale with sqrt(corpus size) instead of fixed top_k fractions, ensuring large conversations retrieve more candidates.
4. **Sliding-scale compression** (5 sentences for top 2, 3 for next 3, 2 for rest) preserves context budget while fitting the larger pool.
5. **Load-bearing fixes kept**: 1024-token generation budget, reasoning_content fallback, minimal prompt, compact formatting, score-first tier sorting.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.61–0.67)
- Failure type movement: Retrieval misses should shrink by 5–10 tasks (turn-level indexing + larger pool bring more gold docs into context). Unknown/abstain should drop by 3–6 (many unknowns are actually retrieval misses). Empty predictions should stay at 0–2. Wrong answers might rise by 1–2 due to noise from larger pool.
- Trace movement: Retrieved hit count should increase (avg > 15). More retrieved docs should contain the gold string for previously missed tasks. Top hits remain well-formatted; lower hits are heavily compressed.
- Side effects to watch: Prompt tokens may rise ~10-20% due to larger retrieval pool. Risk of regression on tasks where the answer requires a contiguous multi-turn block that gets split across turn-level passages; chunk passages and recall window expansion still preserve blocks.

## Falsification
- If retrieval miss count does not drop below 25, the multi-granularity indexing is insufficient or the missed docs are ranked extremely low for other reasons (vocabulary mismatch).
- If passrate does not improve or regresses, the added noise from larger pool or turn-level splitting hurts synthesis more than retrieval gains.
- If empty predictions rise above 4, the prompt/context changes re-introduced hidden-thinking triggers.

