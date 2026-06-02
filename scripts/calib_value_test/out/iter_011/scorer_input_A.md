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
The dominant failure family is list-truncation-induced abstention: when proportional or fixed-window compression cuts off a numbered/bullet list after the first few items, the model sees an incomplete list and answers "unknown." This was observed in `3249768e` (gin cocktail bottles — passed only in iter_006 with fixed 5-sentence window, failed in all proportional/allocation iterations) and `8cf51dda` (endometrial cancer objectives — passed in iter_006/008 with fixed window or highlighting, failed in iter_009/010).

The new mechanism is a structure-aware compression function that:
1. Detects list blocks (numbered, bulleted, or labeled items) inside a retrieved hit.
2. When compressing a list-bearing hit, truncates each item to its heading/first sentence rather than dropping whole items or cutting mid-description. This preserves the complete list skeleton within the per-hit budget.
3. For non-list content, falls back to a fixed 5-sentence contiguous window around the most query-relevant sentence (proven in iter_006).
4. Wraps the peak sentence in `**` to guide the model's attention (observed to help in iter_008).

The prompt stays concise and direct (iter_006 style) to avoid Qwen3 hidden-thinking empty outputs. The 512-token generation budget is retained.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (to ~0.56–0.60)
- Failure type movement: The unknown/abstain cluster should shrink by 4–8 tasks (list-preservation fixes `3249768e`-style failures and focal highlighting reduces missed evidence). Empty predictions should stay at ~3–5 (simple prompt). Wrong-answer count should stay flat or rise by 1–2.
- Trace movement: Compressed hits should show complete list skeletons (e.g., "1. Sweet Vermouth... 2. Dry Vermouth... 3. Campari... 4. Elderflower... 5. Absinthe...") instead of truncated partial lists. Peak sentences should appear wrapped in `**`.
- Side effects to watch: Token consumption should stay similar to iter_006 (~160k) because list-skeleton truncation is aggressive on descriptions. Risk of regressions on tasks where verbose descriptions are needed to disambiguate list items.

## Falsification
- If passrate does not improve or regresses, the list-skeleton truncation may be too aggressive (dropping disambiguating description) or the fixed window may be too narrow for non-list answers.
- If empty predictions rise above 5, the `**` highlighting or list formatting may trigger hidden thinking in Qwen3.
- If the unknown cluster stays flat while list tasks don't improve, the remaining unknowns are genuine retrieval misses and compression cannot compensate.

