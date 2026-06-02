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
The candidate combines three proven elements from earlier iterations—fixed 5-sentence contiguous window (iter_006), peak-sentence highlighting (iter_008), and a simplified direct prompt (iter_006)—and adds a new structure-aware list-skeleton compression function. When a retrieved hit contains a numbered/bulleted/labeled list, the compressor preserves every list item as a heading/first-sentence stub instead of dropping whole items or cutting mid-description. This directly targets the list-truncation-induced abstention family observed in `3249768e` (cocktail bottles — passed only in iter_006, regressed in 008-010) and `8cf51dda` (endometrial cancer objectives — passed in 006/008, regressed in 009/010). The simplified prompt should also reduce empty-prediction failures caused by Qwen3 hidden-thinking (6 empty preds in iter_010 vs 3 in iter_006).

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from 0.53 to ~0.54–0.57)
- Failure type movement: list-truncation abstentions shrink by 2–3 tasks (`3249768e`, `8cf51dda`, and possibly `gpt4_31ff4165` or `gpt4_2f8be40d` if they were partial-list truncation). The empty-prediction cluster should shrink by 2–3 tasks (iter_006-style prompt). Wrong-answer count stays roughly flat.
- Trace movement: Prompt context for list-bearing hits should show complete list skeletons (e.g., all 5 bottles with first-sentence stubs, all 3 objectives with headings) rather than truncated mid-list snippets. Completion traces should show fewer blank outputs and fewer "only the first ... is visible" abstentions.
- Side effects to watch: Token consumption should rise from iter_010's ~154k toward iter_006's ~162k (list skeletons can be longer than aggressive proportional truncation). Risk of 1–2 regressions if list-detection heuristics misfire on non-list content and over-compress prose that needs full detail.

## Falsification
- If passrate does not improve or regresses, the list-skeleton logic either misfires on non-list content causing more harm than good, or the prompt simplification loses needed guidance.
- If `3249768e` and `8cf51dda` still fail, the list-skeleton mechanism is not actually surfacing the complete lists within the per-hit budget.
- If empty predictions stay at ~6, the prompt simplification was ineffective at suppressing Qwen3 hidden-thinking empty outputs.
- If token consumption drops instead of rising, the list skeletons are being aggressively truncated more than the proportional windows they replace.

