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
# GROUND TRUTH for iteration 4

Previous iteration (3) observed:
- passrate: 0.27
- failure clusters: {"correct": 27, "empty": 12, "unknown": 52, "wrong": 9}
- avg prompt/completion tokens: 1813.4 / 176.8

THIS iteration (4) actually observed:
- passrate: 0.49  (over 100 tasks)
- failure clusters: {"correct": 49, "empty": 7, "unknown": 34, "wrong": 10}
- avg prompt/completion tokens: 1408.7 / 162.9
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.6363636363636364, "average_score": 0.6363636363636364}, "single-session-preference": {"count": 4, "passrate": 0.25, "average_score": 0.25}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.23076923076923078, "average_score": 0.23076923076923078}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter004_query_focused_semantic_compression_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter003_token_economical_direct_extraction_top8.json

---
# PREDICTION TO SCORE

# iter_004 prediction

## Candidate
query_focused_semantic_compression

## Mechanism
Iter_004 restores the retrieval-quality fixes that iter_002 proved were load-bearing (score-primary sorting, removal of arbitrary core/summary boosts, RRF normalization, compact core/archival/recall formatting) and layers on top of them the 512-token generation budget and direct-answer prompt from iter_003. The novel component is query-aware per-hit sentence compression: after retrieval, each hit is reduced to the 4 sentences most semantically similar to the query (cosine similarity over tokens), preserving metadata and original sentence order. This replaces the naive 1200-char truncation used in iter_002 and the equitable budget cap used in iter_003, aiming to increase evidence density so more distinct hits fit in the 6000-char context window while preserving answer-bearing content.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (from iter_002's 0.47 to ~0.51–0.57)
  - Lower bound assumes semantic compression is roughly neutral versus iter_002's max_hit_chars=1200, so iter_004 mainly recovers iter_002's 47 passes plus the ~4 tasks that iter_003 uniquely fixed via 512 tokens/direct prompt (0.51).
  - Upper bound assumes sentence compression surfaces more relevant evidence per hit and fits 6–8 hits in context instead of 4–5, fixing an additional 3–6 persistent failures from iter_002 (0.54–0.57).
- Failure type movement:
  - "empty" cluster shrinks from ~18 to <8 (512-token budget + reasoning_content fallback removes truncation empties; 7 historically always-empty tasks may remain).
  - "unknown" cluster shrinks from ~29 to ~20–24 (retrieval ranking restored, so relevant archival/recall hits surface instead of being buried under low-scoring core/summary).
  - "wrong_answer" cluster stable or grows slightly from ~6 to ~7–10 (sentence compression risks dropping a critical sentence from a single long hit, causing 1–3 regressions).
- Trace movement:
  - top_hit_tier_distribution reverts to iter_002 pattern (archival ~70, recall ~30, core/summary near 0) instead of iter_003's core:100.
  - Prompt context includes 6–8 hits vs iter_002's 4–5 and iter_003's ~4.
  - Average prompt tokens drop slightly (~1500–1700) because compact formatting strips XML headers and verbose archival headers.
  - Average completion tokens rise toward ~1800 as the 512 ceiling is actually used for previously truncated tasks.
- Side effects to watch:
  - Risk of wrong-answer regression on tasks where the answer spans >4 sentences in a single hit (e.g., multi-objective or ordered-list questions).
  - Risk that reasoning_content fallback produces verbose non-answers for edge-case tasks where Qwen3 generates thinking tokens but no final content.
  - Token consumption higher than iter_002 due to 512 max_tokens, but lower than iter_003 because compact formatting reduces prompt size.

## Falsification
- Passrate below 0.50 would falsify the mechanism: it would mean either (a) semantic compression destroys more evidence than the naive 1200-char truncation, or (b) the direct-answer prompt + 512-token budget do not combine well with the restored retrieval, causing new synthesis failures.
- Empty predictions remaining ≥12 would suggest the 512-token ceiling and reasoning_content fallback are not the main drivers of empty predictions (contradicting iter_003's observed 12 empties).
- top_hit_tier_distribution still dominated by core/summary would mean the score-primary sorting change in memgpt_scaffold.py was not actually applied or is being overridden by the wrapper scaffold.
- Stable-pass regressions >3 would indicate that sentence compression is too aggressive for this model/judge combination, stripping critical supporting context on already-correct tasks.

