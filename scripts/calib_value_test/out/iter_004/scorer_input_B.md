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
Three coordinated changes on top of a clean source snapshot:

1. **Retrieval score calibration restoration**: Re-applies iter_002's load-bearing scaffold improvements that iter_003 lost—removing arbitrary score boosts (+0.1 core, +0.2 summary), normalizing RRF scores to [0,1], compacting archival/recall formatting, and sorting purely by relevance score. This should recover iter_002's ~0.47 passrate from iter_003's 0.27.

2. **Query-aware per-hit sentence compression**: After retrieval, each hit is compressed to at most 4 sentences ranked by cosine similarity to the query, preserving the first line as metadata. This increases evidence density in the 6000-char budget, allowing more distinct hits to reach the model.

3. **Generation budget and prompt fixes**: Fixes the hidden base.py max_tokens=256 hardcode to 512, adds reasoning_content fallback for Qwen3 hidden thinking, and uses a concise direct-answer prompt ("Do not explain your reasoning").

## Outcome prediction
- Train passrate Δ: [+0.22, +0.26] (from iter_003's 0.27 to ~0.49–0.53). Restoring iter_002's retrieval fixes the 6 regressions and recovers the 0.47 baseline. The 512-token budget and reasoning_content fallback should convert 3–5 of iter_002's 14 empty predictions to passes. Query compression adds a modest +2–4 breakthroughs from persistent fails by fitting more hits in context, while risking 1–3 regressions from destroyed list structure or dropped context.
- Failure type movement:
  - "empty" cluster shrinks from 12 (iter_003) / 14 (iter_002) to 4–6
  - "unknown" cluster stable or shrinks slightly (30 in iter_002 → 26–30)
  - "wrong_answer" cluster stable or grows by ≤2 (4 in iter_002 → 4–6)
- Trace movement:
  - Retrieval scores return to calibrated [0.9–1.0] range for top hits
  - Prompt context includes 6–8 compressed hits vs 4–5 full hits
  - Completion tokens no longer cluster at 256; empty predictions drop
  - Predictions are shorter and more direct due to concise prompt
- Side effects to watch:
  - List-structure questions (e.g., cocktail fifth bottle, grant objectives) may still fail or worsen because space-joined sentence compression destroys list formatting
  - Prompt tokens may rise slightly from more included hits
  - Risk of wrong-answer regression if compression drops disambiguating context from multi-sentence evidence

## Falsification
- Passrate below 0.48 would indicate the query compression is actively harmful or the retrieval restoration is incomplete/mismatched vs iter_002.
- Empty predictions remaining ≥8 would falsify the hypothesis that the 256-token ceiling was the main driver of empty outputs.
- More than 4 regressions from iter_002's pass set would indicate sentence-level compression with space joining is too destructive for this model and task distribution.

