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
# GROUND TRUTH for iteration 19

Previous iteration (18) observed:
- passrate: 0.64
- failure clusters: {"correct": 64, "empty": 3, "unknown": 23, "wrong": 10}
- avg prompt/completion tokens: 1558.5 / 224.2

THIS iteration (19) actually observed:
- passrate: 0.61  (over 100 tasks)
- failure clusters: {"correct": 61, "empty": 2, "unknown": 26, "wrong": 11}
- avg prompt/completion tokens: 1592.6 / 220.2
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 1.0, "average_score": 1.0}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8823529411764706, "average_score": 0.8823529411764706}, "temporal-reasoning": {"count": 26, "passrate": 0.5, "average_score": 0.5}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter019_list_block_extraction_from_long_docs_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter018_contiguous_list_block_preservation_top8_top8.json

---
# PREDICTION TO SCORE

# iter_019 prediction

## Candidate
list_block_extraction_from_long_docs

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, adaptive limits, sentence compression, 1024-token budget, minimal prompt) and replaces the brittle ratio-based list-preservation heuristic with a targeted list-block extraction mechanism. Inside `_compress_hit`, when a document is too long for short-list preservation (>8 units), the new code detects contiguous list blocks (2–6 items), scores them by query relevance, extracts the best block plus ±1 context unit, and bounds the extracted text to `max_sentences + 1` units. This fixes the 8cf51dda regression (3 objectives embedded in a 14-unit grant document) while avoiding the context-budget regressions that iter_018’s `len(units) <= 12` threshold caused.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.07] (from iter_018’s 0.64 to ~0.69–0.71)
- Failure type movement: The ~5 tasks that regressed from iter_016→iter_018 due to context-budget pressure (e.g., 07741c44, 099778bb) should return to passing. The 8cf51dda regression should flip from fail to stable_pass. Persistent_fail count should drop from ~35 to ~29–30. Wrong-answer and empty-prediction clusters should stay flat relative to iter_016.
- Trace movement: For previously regressed tasks, retrieved context should again contain the same high-relevance hits as in iter_016. For 8cf51dda, the context should show the complete 3-item objectives list instead of a truncated/reordered 2-item version. Average prompt tokens should stay near iter_016’s ~1807 level, not spike.
- Side effects to watch: The `max_sentences + 1` bounding is designed to prevent context-bloat, but if implementation bugs loosen the bound, token consumption could rise and push out tail hits. Also watch whether list-block detection misfires on non-list numbered sequences (e.g., years, counts) and causes accidental truncation of narrative context.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or corrupted (same failure mode as iter_018).
- If wrong-answer count rises above iter_016’s baseline (~6/100), the list-block extraction is surfacing noisy or conflicting list content from lower-relevance hits.
- If the 5 tasks that passed in iter_016 but failed in iter_018 remain failed, the `max_sentences + 1` bounding is still consuming too much context budget for those tasks.
- If 8cf51dda remains failed, the list-block detection is not correctly identifying the numbered objectives list within the grant document.

