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

1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, which silently neutralized iter_002's attempt to raise the limit. Raising it to 512 removes the artificial ceiling.

2. **Direct-answer prompt redesign**: Adding "Do not explain your reasoning" suppresses verbose preamble, leaving more budget for the actual answer.

3. **Equitable per-hit context packing**: Dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`) ensures more hits are visible, increasing evidence diversity.

## Outcome prediction
- Train passrate Δ: [+0.07, +0.15] (from 0.47 to ~0.54-0.62)
- Failure type movement:
  - Empty predictions should shrink dramatically (from ~18 to ~3-6)
  - 256-completion-token hits should disappear entirely
  - "unknown" predictions should shrink moderately (from ~29 to ~20-24)
  - Confident-but-wrong predictions may shrink slightly (from ~9 to ~6-8)
- Trace movement:
  - Completion tokens should no longer cluster at 256; distribution should shift leftward and downward as "Do not explain your reasoning" reduces preamble
  - Prompt tokens may stay flat or rise slightly from including more truncated hits
  - Retrieved context should show more distinct hit indices in prompts
- Side effects to watch:
  - Tasks where the answer sits at the end of a previously-included long doc may regress if truncation cuts it off
  - DeepSeek-v4-flash may ignore "Do not explain your reasoning" and still emit thinking tokens, in which case 512 tokens could still be tight for complex reasoning tasks
  - Including more hits could introduce noise on tasks where top-2 docs were already sufficient

## Falsification
If passrate stays below 0.53, the mechanism is falsified: either the 256-token empty predictions are caused by an API-level thinking-token behavior that max_tokens cannot fix, or equitable truncation is cutting off critical answer-bearing spans in long docs. If empty predictions remain above 10, the token-limit theory is wrong.

