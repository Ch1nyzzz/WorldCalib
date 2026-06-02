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
# GROUND TRUTH for iteration 3

Previous iteration (2) observed:
- passrate: 0.47
- failure clusters: {"correct": 47, "empty": 18, "unknown": 29, "wrong": 6}
- avg prompt/completion tokens: 1478.0 / 148.7

THIS iteration (3) actually observed:
- passrate: 0.27  (over 100 tasks)
- failure clusters: {"correct": 27, "empty": 12, "unknown": 52, "wrong": 9}
- avg prompt/completion tokens: 1813.4 / 176.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.5333333333333333, "average_score": 0.5333333333333333}, "multi-session": {"count": 27, "passrate": 0.2222222222222222, "average_score": 0.2222222222222222}, "single-session-assistant": {"count": 11, "passrate": 0.36363636363636365, "average_score": 0.36363636363636365}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.47058823529411764, "average_score": 0.47058823529411764}, "temporal-reasoning": {"count": 26, "passrate": 0.038461538461538464, "average_score": 0.038461538461538464}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter003_token_economical_direct_extraction_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter002_memgpt_calibrated_ranking_top10.json

---
# PREDICTION TO SCORE

# iter_003 prediction

## Candidate
token_economical_direct_extraction

## Mechanism
Three coordinated changes on top of the clean snapshot:
1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, silently overriding model.py's 512 default. Raising base.py to 512 removes the artificial ceiling that caused 18 empty predictions in iter_002 (all hitting exactly 256 completion tokens).
2. **Direct-answer prompt redesign**: Adds "Do not explain your reasoning" to suppress verbose preamble and hidden thinking tokens, leaving more of the 512-token budget for the actual answer.
3. **Equitable per-hit context packing**: Replaces the "include full hits until budget exhausted" strategy with dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`), ensuring 6–8 hits are visible rather than 2–3 long hits crowding out the rest.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.16] (from iter_002's 0.47 to ~0.57–0.63)
- Failure type movement:
  - Empty predictions: should shrink from 18 to 4–7. The 512-token ceiling plus the reasoning suppression should convert the majority of truncation failures into completed outputs.
  - Unknown/abstain cluster: should shrink modestly from 23 wrong unknowns to ~19–21, as equitable packing surfaces additional relevant docs that were previously dropped from the 6000-char context window.
  - Wrong-answer count: should stay flat at ~6 or rise by at most 1–2, because hit truncation can cut off list items or late-sentence answers in long documents.
- Trace movement:
  - Completion tokens should become bimodal: most tasks still use <200 tokens, but the previously-empty cluster should now show 300–450 tokens.
  - Prompt tokens should stay similar (~1500–1700) because total context budget is unchanged; the difference is that budget is spread across more hits.
  - Retrieved context should show 6–8 hits included instead of the 3–5 typical in iter_002.
- Side effects to watch:
  - If Qwen3 generates hidden thinking tokens regardless of the prompt directive, some tasks may still burn the 512-token budget and return empty or truncated outputs.
  - Dynamic truncation of long hits could regress list-type answers (e.g., enumerations) if the answer-bearing item falls beyond the truncation boundary.
  - The `reasoning_content` fallback added in iter_002 may interact unpredictably with the new prompt; if the model emits reasoning into `reasoning_content` and nothing into `content`, the fallback could surface reasoning text instead of the answer.

## Falsification
- If passrate stays below 0.53, the mechanism is falsified: either the 512-token budget is insufficient to overcome Qwen3 hidden-thinking truncation, or equitable packing causes more regressions than the empty-prediction fixes deliver.
- If empty predictions do not drop below 10, the "Do not explain your reasoning" directive is ineffective at suppressing hidden token consumption, and the true bottleneck is model-level reasoning that a larger token budget alone cannot fix.
- If the unknown cluster does not shrink at all (or grows), the context-packing trade-off is net-negative: the loss of full-hit context for top-ranked documents outweighs the gain from including tail hits.

