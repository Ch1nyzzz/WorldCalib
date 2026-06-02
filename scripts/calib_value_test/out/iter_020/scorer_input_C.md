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
# GROUND TRUTH for iteration 20

Previous iteration (19) observed:
- passrate: 0.61
- failure clusters: {"correct": 61, "empty": 2, "unknown": 26, "wrong": 11}
- avg prompt/completion tokens: 1592.6 / 220.2

THIS iteration (20) actually observed:
- passrate: 0.69  (over 100 tasks)
- failure clusters: {"correct": 69, "empty": 4, "unknown": 20, "wrong": 7}
- avg prompt/completion tokens: 1600.6 / 221.4
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8666666666666667, "average_score": 0.8666666666666667}, "multi-session": {"count": 27, "passrate": 0.5185185185185185, "average_score": 0.5185185185185185}, "single-session-assistant": {"count": 11, "passrate": 1.0, "average_score": 1.0}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.9411764705882353, "average_score": 0.9411764705882353}, "temporal-reasoning": {"count": 26, "passrate": 0.5769230769230769, "average_score": 0.5769230769230769}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter020_multi_objective_compression_with_answer_type_scoring_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter019_list_block_extraction_from_long_docs_top8.json

---
# PREDICTION TO SCORE

# iter_020 prediction

## Candidate
multi_objective_compression_with_answer_type_scoring

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, multi-granularity archival, adaptive limits, 1024-token budget, minimal prompt). Replaces single-objective sentence compression in `_compress_hit` with a multi-objective score (0.65 relevance cosine + 0.35 answer-type likelihood). Answer-type heuristics boost sentences containing numbers for quantitative questions, dates/time words for temporal questions, yes/no markers for binary questions, and list markers for enumeration questions. Compressed units are joined with newlines instead of spaces. The system prompt is also softened from "contains the answer" to "contains the answer or enough facts to infer it."

## Outcome prediction
- Train passrate Δ: [+0.00, +0.03] (to ~0.69–0.72)
- Failure type movement: The list-truncation cluster (8cf51dda) should convert from persistent fail to pass because list-marker boosting preserves all three objectives. The empty-prediction regression seen in iter_019 (0db4c65d) should revert to pass because the exact iter_016 stack is restored. A small number of quantitative persistent fails (e.g., 129d1232 total-money, 157a136e grandma-age) may flip if number boosting surfaces answer-bearing sentences that pure cosine buried. The broad "unknown" cluster (retrieval failures like 0edc2aef, 195a1a1b) should stay flat because compression cannot fix missing retrieval.
- Trace movement: For 8cf51dda, compressed context should now show all three numbered objectives instead of two. For quantitative and temporal tasks, traces should show more number/date-bearing sentences in the top compressed slots. Newline separators should be visible between compressed units. The inference prompt may produce slightly more inferential phrasing (e.g., "Based on X and Y, the answer is Z") on under-specified questions.
- Side effects to watch: The 0.35 weight on answer-type heuristics could occasionally boost an irrelevant sentence that happens to contain a number or date, displacing a more relevant prose sentence. The softened inference prompt could increase hallucinated answers on tasks where retrieval is poor. Token consumption should remain roughly flat (~180K).

## Falsification
- If passrate does not reach at least 0.68, the iter_016 stack restoration was incomplete or the answer-type scoring introduced regressions that overpower the gains.
- If the wrong-answer count rises by more than 2–3 tasks, the answer-type heuristics are producing false positives (irrelevant sentences with surface markers crowding out truly relevant ones).
- If empty predictions increase, there is a bug in the prompt or compression pipeline.

