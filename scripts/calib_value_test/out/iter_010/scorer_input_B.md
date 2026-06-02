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
# GROUND TRUTH for iteration 10

Previous iteration (9) observed:
- passrate: 0.54
- failure clusters: {"correct": 54, "empty": 8, "unknown": 32, "wrong": 6}
- avg prompt/completion tokens: 1523.6 / 166.8

THIS iteration (10) actually observed:
- passrate: 0.53  (over 100 tasks)
- failure clusters: {"correct": 53, "empty": 6, "unknown": 29, "wrong": 12}
- avg prompt/completion tokens: 1354.2 / 184.2
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.48148148148148145, "average_score": 0.48148148148148145}, "single-session-assistant": {"count": 11, "passrate": 0.6363636363636364, "average_score": 0.6363636363636364}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8235294117647058, "average_score": 0.8235294117647058}, "temporal-reasoning": {"count": 26, "passrate": 0.3076923076923077, "average_score": 0.3076923076923077}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter010_answer_type_boosted_retrieval_with_proportional_context_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter009_cross_hit_evidence_distillation_top8.json

---
# PREDICTION TO SCORE

# iter_010 prediction

## Candidate
answer_type_boosted_retrieval_with_proportional_context

## Mechanism
The candidate layers two retrieval-side and context-packing changes on top of the proven dual-pass retrieval and simplified formatting from iter_006/008:

1. **Answer-type-aware retrieval boosting**: After dual-pass retrieval, detect the expected answer type from the question (numbers, dates, percentages, lists) using lightweight regex heuristics. Boost the scores of retrieved hits that contain matching patterns by 15%. This operates entirely in the retrieval tier without adding prompt complexity.

2. **Score-proportional context allocation**: Instead of compressing every hit to a fixed window, allocate the global `max_context_chars` budget proportionally to each hit's relevance score (minimum 200 chars floor). Within each budget, a contiguous window around the most query-relevant sentence is preserved. This ensures high-confidence evidence is shown in full while low-scoring hits are abbreviated.

The prompt is kept concise and direct (iter_006 style, no cross-hit excerpts) and the 512-token generation budget is retained to avoid Qwen3 hidden-thinking truncation.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.55–0.57)
- Failure type movement:
  - Empty-prediction cluster should shrink from ~10 (iter_009) to ~6–8 because the simpler prompt avoids triggering hidden thinking compared to iter_009's cross-hit excerpts.
  - Unknown/abstain cluster should shrink modestly (by ~2–4 tasks) because proportional allocation preserves more of the top hit's content, converting some synthesis failures where the answer was buried in a highly-ranked but truncated document.
  - Wrong-answer count should stay flat (~7–9) since the mechanism does not introduce new hallucination pressure.
- Trace movement:
  - Retrieved document lists should show the same dual-query fusion as iter_008/009, but with slightly reordered ranks when answer-type patterns match.
  - Prompt spans should show variable-length hit blocks (high-score hits longer, tail hits shorter) rather than uniform compression.
  - No "excerpts" or "focal" sections should appear in the prompt — the prompt remains a simple enumerated list of hits.
- Side effects to watch:
  - Proportional allocation may regress 1–3 previously-passing tasks if the score distribution is flat and the floor budget crowds out a critical sentence that a fixed wider window would have preserved.
  - Token consumption should stay roughly flat vs iter_009 (~1690 avg) because the total context budget is unchanged; completion tokens may drop slightly with the simpler prompt.

## Falsification
- If passrate does not improve or regresses, the answer-type boost is either too weak (15%) to reorder gold-bearing docs into the top hits, or the proportional allocation is fragmenting evidence across hits in a way that hurts synthesis.
- If empty predictions stay at ~10, the issue is not prompt verbosity but the 512-token generation ceiling or a deeper Qwen3 serving-layer bug, and the simpler prompt change was ineffective.
- If the unknown cluster stays flat while empty predictions drop, the remaining unknowns are genuine retrieval misses (gold docs outside the top-8 pool) that boosting cannot fix, confirming retrieval coverage is the dominant failure family.

