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
Three coordinated changes that address the dominant failure families in iter_002:

1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, which silently neutralized iter_002's attempt to raise the limit. This hard cap caused 18 empty predictions (all hitting exactly 256 completion tokens) and capped every other task at ≤256 tokens. Raising it to 512 removes the artificial ceiling.

2. **Direct-answer prompt redesign**: The current prompt lets the model generate reasoning before "FINAL ANSWER:", wasting tokens and increasing truncation risk. Adding "Do not explain your reasoning" suppresses verbose preamble, leaving more budget for the actual answer.

3. **Equitable per-hit context packing**: The current builder includes full hits until the 6000-char budget is exhausted, so a single 1700-char hit can crowd out 2-3 other relevant docs. Dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`) ensures more hits are visible, increasing evidence diversity.

## Outcome prediction
- Train passrate Δ: [+0.06, +0.12] (from 0.47 to ~0.53–0.59)
- Failure type movement:
  - "empty" cluster shrinks from 18 to <5
  - "unknown" cluster shrinks from 29 to ~20–24 (sub-family where gold is present in context)
  - "wrong_answer" cluster stable or grows by ≤2
- Trace movement:
  - No completion_tokens ceiling at 256
  - Prompt context includes more hits (7–8 vs 4–5)
  - Predictions are shorter and more direct
- Side effects to watch:
  - Completion tokens rise for previously empty tasks
  - Prompt tokens may rise slightly from more included hits
  - Risk of wrong-answer regression if model becomes over-confident

## Falsification
- Passrate below 0.52 falsifies the mechanism (the 256-token ceiling was not the main driver of empty predictions, or evidence diversity doesn't improve synthesis).
- Empty predictions remaining ≥10 suggests Qwen3 generates hidden thinking tokens regardless of max_tokens.
- Stable-pass regressions >2 indicate the direct-answer prompt is too aggressive for multi-line answers.

