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
The dominant failure family in iter_012 is retrieval misses: the gold answer is absent from all retrieved hits in roughly 30 of 43 failures. The new mechanism adds turn-level archival indexing alongside chunk-level passages, runs four-pass retrieval (BM25+cosine on both indexes with full and keyword-only queries), fuses rankings with RRF, and scales retrieval limits with sqrt(corpus size) instead of fixed top_k. This directly increases recall for large conversations and reduces relevance dilution when a relevant turn shares a chunk with irrelevant neighbors.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.61–0.67)
- Failure type movement: The retrieval-miss cluster should shrink by 6–12 tasks, converting persistent fails into breakthroughs. Tasks like 10d9b85a (April workshops) and 129d1232 (charity total) are high-probability fixes because keyword-only queries and turn-level indexing surface scattered mentions. Wrong-answer count should drop slightly as more complete evidence reaches the model. Empty predictions should stay flat or rise by at most 1 (the 1024-token budget and minimal prompt from iter_012 are preserved).
- Trace movement: Average retrieved count per task should rise from ~15 to ~20–25, with a larger share coming from archival memory. Traces should show more "turn"-tagged passages and broader coverage of large conversations. Top-hit relevance should improve for tasks where the gold was previously ranked outside the fixed top_k window.
- Side effects to watch: Token consumption will rise modestly because more candidates are retrieved, but sliding-scale compression (5/3/2 sentences) caps the growth. Risk of regressions is low because RRF fusion is robust and top hits still receive generous compression budgets, but 1–2 previously correct tasks could regress if keyword queries boost noisy passages into the top ranks.

## Falsification
- If passrate does not improve or regresses, the four-pass RRF fusion is either too noisy (keyword queries surfacing irrelevant docs) or the sliding compression on ranks 6+ is dropping critical evidence before the model sees it.
- If empty predictions rise above 4, the larger retrieval pool is overwhelming the model despite the minimal prompt; this would suggest a context-length or attention-dilution issue.
- If retrieval-miss tasks like 1a1907b4 (cocktail suggestions) and 10d9b85a (April workshops) remain failed with the same irrelevant top hits, the turn-level index and keyword queries are not helping semantic-mismatch cases, and the benefit is limited to lexical-surface fixes.

