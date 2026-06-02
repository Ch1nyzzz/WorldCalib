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
# GROUND TRUTH for iteration 11

Previous iteration (10) observed:
- passrate: 0.53
- failure clusters: {"correct": 53, "empty": 6, "unknown": 29, "wrong": 12}
- avg prompt/completion tokens: 1354.2 / 184.2

THIS iteration (11) actually observed:
- passrate: 0.47  (over 100 tasks)
- failure clusters: {"correct": 47, "empty": 10, "unknown": 34, "wrong": 9}
- avg prompt/completion tokens: 1504.2 / 187.3
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.2962962962962963, "average_score": 0.2962962962962963}, "single-session-assistant": {"count": 11, "passrate": 0.5454545454545454, "average_score": 0.5454545454545454}, "single-session-preference": {"count": 4, "passrate": 0.25, "average_score": 0.25}, "single-session-user": {"count": 17, "passrate": 0.8235294117647058, "average_score": 0.8235294117647058}, "temporal-reasoning": {"count": 26, "passrate": 0.23076923076923078, "average_score": 0.23076923076923078}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter011_fixed_window_list_skeleton_highlighting_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter010_answer_type_boosted_retrieval_with_proportional_context_top8.json

---
# PREDICTION TO SCORE

# iter_011 prediction

## Candidate
fixed_window_list_skeleton_highlighting

## Mechanism
Reverts from iter_010's proportional context allocation and answer-type boosting back to the proven iter_008 stack (fixed 5-sentence contiguous window + `**` peak-sentence highlighting, concise prompt, 512-token budget, dual-pass keyword-augmented retrieval). Adds one new compression rule: when a hit contains list items (numbered/bulleted/labeled), the complete list skeleton is preserved by truncating each item to its heading/first 10 words rather than dropping whole items or cutting mid-description. Non-list content falls back to the fixed 5-sentence window.

The mechanism targets the list-truncation-induced abstention family observed in iter_008/010: when compression cuts a numbered list after the first few items, the model sees an incomplete list and answers "unknown." This specifically should recover 3249768e (cocktail fifth bottle, failed in iter_008/010) and 8cf51dda (endometrial cancer objectives, regressed in iter_010). It should not affect tasks without list-bearing hits.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.54–0.56)
- Failure type movement: The unknown/abstain cluster should shrink by 2–4 tasks (list-truncation fixes for 3249768e and 8cf51dda, plus any other list-bearing persistent fails). Empty predictions should stay flat at ~3–5 (same concise prompt and 512-token budget as iter_008). Wrong-answer count should stay flat or rise by at most 1.
- Trace movement: Retrieved context for list-bearing hits should show all list items with truncated headings (e.g., "1. Sweet Vermouth ... 5. Absinthe ...") instead of mid-list cuts. Peak sentences should be wrapped in `**`. Non-list hits should show fixed 5-sentence windows.
- Side effects to watch: Token consumption should be similar to iter_008 (~1600 avg, lower than iter_010's ~1540 because proportional allocation is removed). Risk of context-budget regressions is low because list items are capped at 10 words each, but if a hit contains many list items it could crowd out later hits.

## Falsification
- If passrate does not improve or regresses, list skeleton preservation either fails to fix the target tasks (e.g., the relevant list is still truncated by sentence-splitting heuristics) or causes regressions by expanding list-bearing hits and dropping other evidence.
- If the unknown cluster stays flat while the target tasks remain in persistent_fail, the list-truncation diagnosis is wrong and the abstention is caused by something else (retrieval miss or prompt conservatism).
- If empty predictions rise above ~5, the `**` highlighting or list-preservation logic is triggering Qwen3 hidden thinking, indicating the prompt tier is not as safe as iter_008.

