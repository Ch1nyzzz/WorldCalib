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
# GROUND TRUTH for iteration 5

Previous iteration (4) observed:
- passrate: 0.49
- failure clusters: {"correct": 49, "empty": 7, "unknown": 34, "wrong": 10}
- avg prompt/completion tokens: 1408.7 / 162.9

THIS iteration (5) actually observed:
- passrate: 0.39  (over 100 tasks)
- failure clusters: {"correct": 39, "empty": 3, "unknown": 48, "wrong": 10}
- avg prompt/completion tokens: 1318.9 / 149.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.14814814814814814, "average_score": 0.14814814814814814}, "single-session-assistant": {"count": 11, "passrate": 0.8181818181818182, "average_score": 0.8181818181818182}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.07692307692307693, "average_score": 0.07692307692307693}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter005_structure_preserving_adaptive_context_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter004_query_focused_semantic_compression_top8.json

---
# PREDICTION TO SCORE

# iter_005 prediction

## Candidate
structure_preserving_adaptive_context

## Mechanism
Replace fixed 4-sentence per-hit compression with structure-aware adaptive context assembly: list-atomic compression (preserve entire list blocks when any item is query-relevant), dynamic relevance-weighted sentence budgets (3/5/8 sentences by confidence), archival list preservation, and a softer abstention prompt.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (from iter_004’s 0.49 baseline to ~0.52–0.56)
- Failure type movement:
  - "unknown" cluster shrinks by 3–6 (list-atomic fixes over-abstention on truncated lists; softer prompt reduces scattered-evidence abstentions)
  - "wrong_answer" cluster shrinks by 2–4 (8fb83627 and similar list-counting errors should recover when full lists are preserved)
  - "empty" cluster stable or shrinks by 0–1 (remaining empties are mostly hard generation-boundary issues not directly targeted)
- Trace movement:
  - Predictions for list-related queries will contain full enumerations instead of "unknown"
  - Completion tokens for high-confidence hits will be longer (up to 8 sentences vs flat 4)
  - Prompt context may include slightly fewer total hits because list preservation consumes more characters per hit
- Side effects to watch:
  - Prompt token count may rise 5–15% from preserved lists, potentially crowding out tail hits
  - Risk of extracting wrong list item if model picks wrong element from a preserved multi-item list
  - Softer abstention could increase hallucinated answers on genuine retrieval misses

## Falsification
- Passrate below 0.51 would refute the claim that list-atomic compression recovers the iter_004 regressions (8cf51dda, 8fb83627)
- "unknown" cluster shrinking by fewer than 2 would mean the softer abstention prompt has no measurable effect and list truncation was not a dominant abstention cause
- New regressions in non-list tasks would indicate context crowding from longer hits is outweighing the list-preservation benefit

