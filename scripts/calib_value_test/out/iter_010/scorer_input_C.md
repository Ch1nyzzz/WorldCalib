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
The candidate removes cross-hit evidence distillation (iter_009) and returns to the concise iter_006-style prompt while keeping dual-pass retrieval from iter_008. It adds two retrieval-side changes:
1. Answer-type-aware boosting (15% score boost for hits containing number/date/percentage/list patterns matching the question type)
2. Score-proportional context allocation (distributing max_context_chars by relevance score share with a 200-char floor, preserving a contiguous window around the most query-relevant sentence per hit)

## Outcome prediction
- Train passrate Δ: [+0.01, +0.05] (to ~0.55–0.59)
- Failure type movement: The "unknown despite relevant docs" cluster should shrink modestly (by 2–4 items) as answer-type boosting pushes evidence-bearing passages higher. The empty-prediction cluster should stay flat or shrink slightly because the concise prompt avoids hidden-thinking triggers. Pure retrieval-miss failures (e.g., Miami hotel, April workshops) will remain unchanged.
- Trace movement: Spans should show variable-length hits proportional to scores instead of uniformly compressed hits. No "Relevant excerpts" section at the top of prompts (that was iter_009). Completion tokens should stay in the 60–350 range; no spike in 512-token completions.
- Side effects to watch: Token consumption may drop slightly due to more efficient budget allocation, or shift higher for tasks where a single high-score doc dominates. Risk of regression on list/objective questions if the 200-char floor is too small for low-scoring but necessary supporting docs.

## Falsification
- If passrate stays flat or drops, the 15% boost is too weak to reorder meaningful ranks, or proportional allocation loses more signal from low-scoring docs than it gains from high-scoring ones, and the removal of cross-hit distillation is not compensated.
- If empty predictions rise above the iter_009 level (~3–5 tasks), the prompt or context-packing change is somehow more prone to triggering Qwen3 hidden thinking despite being concise.
- If the "unknown despite relevant docs" cluster does not shrink, the regex-based answer-type detection is not actually surfacing the answer-bearing passages, indicating the failure is synthesis-level rather than ranking-level.

