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
# GROUND TRUTH for iteration 6

Previous iteration (5) observed:
- passrate: 0.39
- failure clusters: {"correct": 39, "empty": 3, "unknown": 48, "wrong": 10}
- avg prompt/completion tokens: 1318.9 / 149.8

THIS iteration (6) actually observed:
- passrate: 0.5  (over 100 tasks)
- failure clusters: {"correct": 50, "empty": 3, "unknown": 38, "wrong": 9}
- avg prompt/completion tokens: 1448.5 / 170.9
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.25, "average_score": 0.25}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.19230769230769232, "average_score": 0.19230769230769232}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter006_contiguous_window_compression_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter005_structure_preserving_adaptive_context_top8.json

---
# PREDICTION TO SCORE

# iter_006 prediction

## Candidate
contiguous_window_compression

## Mechanism
Replace iter_005's destructive list-block preservation with bounded contiguous relevance windows (max 5 sentences centered on peak query-similarity sentence), re-apply iter_004's calibrated retrieval scaffold (normalized RRF, no arbitrary boosts, compact formatting, 300-char archival truncation), and add a synthesis-permissive prompt that explicitly permits combining facts across passages and simple arithmetic.

## Outcome prediction
- Train passrate Δ: [+0.08, +0.15] (from iter_005's 0.39 baseline to ~0.47–0.54)
- Failure type movement:
  - "unknown" cluster shrinks by 8–14 (recovering the synthesis/abstention regressions introduced by iter_005's context bloat)
  - "wrong_answer" cluster stable or grows by 1–2 (synthesis prompt may occasionally misfire)
  - Empty cluster stable (~3 tasks)
- Trace movement:
  - More predictions contain arithmetic/combination phrases ("$120 + $20 = $140", "40% is higher than 20%")
  - Prompt tokens drop from iter_005's ~1,319 avg toward iter_004's ~1,409 avg or slightly below because per-hit length is tightly bounded
  - Fewer "unknown FINAL ANSWER: unknown" outputs
- Side effects to watch:
  - Risk of losing 1–2 iter_005 breakthroughs (e.g., 8cf51dda grant objectives) if a contiguous 4-sentence window truncates a long list that list-preservation previously kept whole
  - Risk of occasional wrong synthesis when the model combines unrelated numbers from different hits
  - Token consumption should decrease compared to iter_005 because full list blocks are no longer preserved

## Falsification
- Passrate below 0.45 would mean contiguous windows discard more relevant signal than iter_005's list-preservation added, or that the retrieval-scaffold revert failed to restore correct ranking
- "unknown" cluster shrinking by fewer than 5 would refute the core diagnosis that iter_005's failures were primarily abstention caused by context bloat
- Wrong-answer cluster growing by more than 3 would mean the synthesis-permissive prompt causes harmful hallucination on scattered-evidence tasks

