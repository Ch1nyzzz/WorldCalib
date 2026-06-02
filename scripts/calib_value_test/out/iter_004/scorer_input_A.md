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
Query-focused semantic sentence compression layered on calibrated retrieval ranking and a 512-token generation budget.

1. **Retrieval score calibration** (supporting infrastructure): Remove arbitrary score boosts (+0.1 core, +0.2 summary), normalize RRF scores to [0,1], sort hits purely by relevance score, and compact archival/recall formatting. This restores the retrieval quality that iter_002 proved was load-bearing and that iter_003 catastrophically lost.

2. **Query-aware per-hit sentence compression** (novel mechanism): After retrieval, each hit is compressed by keeping only the 4 sentences most semantically relevant to the query (cosine similarity over tokens), preserving the first line as metadata and restoring original sentence order. This maximizes evidence density: more distinct hits fit in the 6000-char context budget, and the model sees less noise per hit.

3. **Generation budget liberation**: Fix the hidden base.py max_tokens=256 hardcode to 512, add reasoning_content fallback for Qwen3, and keep a concise direct-answer prompt.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.20] (from iter_002’s 0.47 baseline to ~0.57–0.67)
- Failure type movement:
  - "unknown" cluster shrinks by 8–15 (gold evidence is now more salient within compressed hits)
  - "empty" cluster shrinks from ~25 to <5 (512-token budget removes truncation)
  - "wrong_answer" cluster stable or shrinks slightly (better evidence focus reduces picking wrong passages)
- Trace movement:
  - Completion tokens exceed 256 for many previously empty tasks
  - Prompt context includes more hits (8–12 vs 4–6) because each hit is shorter
  - Predictions more often use exact words from context
- Side effects to watch:
  - Prompt tokens may rise slightly from more included hits
  - Risk of dropping relevant cross-sentence context in rare cases where the answer spans >4 sentences in one hit

## Falsification
- Passrate below 0.52 would suggest sentence compression hurts coherence or that ranking calibration is insufficient
- Empty predictions remaining ≥10 would indicate the 512-token budget is still inadequate for some task types
- "unknown" cluster not shrinking would mean the dominant failure is retrieval miss (gold not in top-K) rather than evidence salience

