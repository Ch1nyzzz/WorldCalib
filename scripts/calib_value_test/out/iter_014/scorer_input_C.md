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
# GROUND TRUTH for iteration 14

Previous iteration (13) observed:
- passrate: 0.63
- failure clusters: {"correct": 63, "empty": 3, "unknown": 25, "wrong": 9}
- avg prompt/completion tokens: 1651.5 / 208.1

THIS iteration (14) actually observed:
- passrate: 0.66  (over 100 tasks)
- failure clusters: {"correct": 66, "empty": 4, "unknown": 18, "wrong": 12}
- avg prompt/completion tokens: 1656.4 / 238.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.9333333333333333, "average_score": 0.9333333333333333}, "multi-session": {"count": 27, "passrate": 0.5185185185185185, "average_score": 0.5185185185185185}, "single-session-assistant": {"count": 11, "passrate": 0.6363636363636364, "average_score": 0.6363636363636364}, "single-session-preference": {"count": 4, "passrate": 0.25, "average_score": 0.25}, "single-session-user": {"count": 17, "passrate": 0.9411764705882353, "average_score": 0.9411764705882353}, "temporal-reasoning": {"count": 26, "passrate": 0.5384615384615384, "average_score": 0.5384615384615384}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter014_list_atomic_compression_with_directive_prompt_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter013_multi_granularity_adaptive_retrieval_top8.json

---
# PREDICTION TO SCORE

# iter_014 prediction

## Candidate
list_atomic_compression_with_directive_prompt

## Mechanism
Two bounded changes atop the iter_013 multi-granularity retrieval scaffold:
1. **List-atomic compression**: In `build_answer_messages`, top-2 hits containing structured lists with 3+ items get a dynamic sentence budget of `list_items + 2` (instead of fixed 5) when the question matches list-related `_answer_type_patterns`. This preserves complete list blocks in context while keeping per-hit length bounded.
2. **Directive prompt tweak**: The system prompt shifts from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (to ~0.64–0.67)
- Failure type movement: Unknown/abstain failures should shrink by 2–4 tasks (the two canonical fixes—3249768e list truncation and 8aef76bc synthesis conservatism—plus 0–2 additional partial-evidence abstentions). Retrieval-miss unknowns (~14 tasks with genuinely no relevant info) should remain unchanged. Wrong-answer failures might rise by 0–1 if the prompt makes the model over-confident on partial evidence (e.g., 60036106 or 5025383b). Empty predictions should stay flat.
- Trace movement: Top-2 hits for list questions should show expanded sentence windows. Fewer traces should end with "FINAL ANSWER: unknown" when retrieved docs contain partial but directly relevant information.
- Side effects to watch: Prompt tokens stay roughly unchanged (same `max_context_chars`). Completion tokens may tick up slightly as the model produces substantive answers instead of "unknown." Risk of regression on the 6 true-negative tasks that passed with "unknown" in iter_013 is low because those contexts genuinely contain no relevant information at all, so the new wording still permits unknown.

## Falsification
- If passrate does not improve or regresses, the prompt wording is either too subtle to change model behavior or the increased willingness to guess converts partial-evidence unknowns into wrong answers at a higher rate than expected.
- If unknown failure count does not drop below 23, the prompt change is insufficient to overcome the model's abstention bias on partial evidence.
- If empty predictions rise above 4, the broader context or prompt length is somehow triggering output failures.

