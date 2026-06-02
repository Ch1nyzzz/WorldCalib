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
The dominant failure family from iter_013 is synthesis failures where evidence is present in retrieved hits but the model either abstains or extracts a truncated answer. Two independent evidence sources support this:
1. Task 3249768e (cocktail fifth bottle): the correct doc with Absinthe is retrieved and re-sorted to the top by answer-signal boosting, but sliding-scale sentence-window compression (5 sentences max) truncates the 5-item list to 4 items, cutting off Absinthe. The model explicitly says "only the first bottle (Sweet Vermouth) is mentioned."
2. Task 8aef76bc (sealant): "Mod Podge or another sealant" appears in a top-ranked recall doc, yet the model outputs "Unknown," indicating synthesis conservatism.

The new mechanism has two parts:
1. **List-atomic compression**: In `build_answer_messages`, when a top hit (idx ≤ 2) contains a structured list with 3+ items and the question asks for a list-related answer (detected by existing `_answer_type_patterns`), the compression budget is expanded to `list_items + 2` sentences instead of the fixed 5. This preserves the complete list block while still bounding per-hit length.
2. **Directive prompt tweak**: The system prompt is changed from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

Both changes are bounded: list expansion applies only to top-2 hits with clear list structure, and the prompt change is a wording shift, not a reasoning chain addition, so it should not trigger Qwen3 hidden thinking.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (to ~0.66–0.70)
- Failure type movement: Unknown/abstain cluster should shrink by 3–5 tasks (list truncation fixes + reduced conservatism). Wrong answers might rise by 0–1 due to the more directive prompt. Empty predictions should stay at 0–3.
- Trace movement: For previously failed list questions, the full list block should now appear in the compressed prompt instead of a truncated window. For sealant-type tasks, predictions should shift from "unknown" to the extracted phrase.
- Side effects to watch: Prompt tokens may rise ~5% due to longer list blocks in top hits, but avg prompt tokens in iter_013 was 1639 with headroom. Risk of regression on tasks where a long list crowds out other hits is low because list expansion is capped at top-2 hits.

## Falsification
- If passrate does not improve or regresses, either the prompt wording triggers more hidden thinking / wrong answers, or the list-preservation crowds out critical evidence from other hits.
- If the unknown cluster does not shrink by at least 2 tasks, the synthesis failures are driven by something other than list truncation and prompt conservatism (e.g., vocabulary mismatch between query and evidence).
- If empty predictions rise above 5, the prompt change re-introduced Qwen3 hidden-thinking truncation.

