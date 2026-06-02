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
The dominant failure families are: (1) empty predictions caused by Qwen3 hidden thinking triggered by complex prompts, and (2) retrieval misses / synthesis failures where gold evidence is either not ranked highly enough or gets truncated by fixed per-hit compression.

The new mechanism layers two retrieval-side and context-packing changes on top of proven dual-pass retrieval and simplified formatting:

1. **Answer-type-aware retrieval boosting**: After dual-pass retrieval, detect the expected answer type from the question (numbers, dates, percentages, lists) using lightweight regex heuristics. Boost the scores of retrieved hits that contain matching patterns by 15%. This is general — any retrieval-based QA system benefits from ranking answer-bearing documents higher.

2. **Score-proportional context allocation**: Instead of compressing every hit to a fixed window or showing them at full length, allocate the global `max_context_chars` budget proportionally to each hit's relevance score. Each hit receives a minimum floor (200 chars), and the remainder is distributed by score share. Within each budget, a contiguous window around the most query-relevant sentence is preserved. This ensures high-confidence evidence is preserved in full while low-scoring hits are abbreviated, maximizing the chance the model sees the critical evidence.

The prompt is kept concise and direct (iter_006 style, without cross-hit excerpts) to avoid triggering hidden thinking. The 512-token generation budget is retained.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.58–0.64)
- Failure type movement: The empty-prediction cluster should shrink from 8 to 3–4 (simple prompt reduces hidden thinking). The unknown cluster should shrink by 4–8 tasks (answer-type boosting surfaces gold evidence higher, and proportional allocation preserves it better). Wrong-answer count should stay flat or rise slightly.
- Trace movement: Retrieval docs should show re-ordered rankings where answer-bearing docs move up. Prompt context should show variable-length hits — high-scoring docs are longer, low-scoring docs are shorter.
- Side effects to watch: Token consumption should drop slightly because low-scoring hits are more aggressively truncated. Risk of regressions on tasks requiring synthesis across many low-scoring hits (but minimum floor preserves them).

## Falsification
- If passrate does not improve or regresses, the answer-type patterns may be too noisy or the proportional allocation may be crowding out cross-hit synthesis.
- If empty predictions stay at ~8, the issue is not prompt complexity but a deeper serving-layer bug, and the simpler prompt was ineffective.
- If the unknown cluster stays flat while empty predictions drop, the remaining unknowns are genuine retrieval misses and boosting cannot compensate.

