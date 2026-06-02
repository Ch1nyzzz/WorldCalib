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
# GROUND TRUTH for iteration 5

Previous iteration (4) observed:
- passrate: 0.49
- failure clusters: {"correct": 49, "empty": 7, "unknown": 34, "wrong": 10}
- avg prompt/completion tokens: 1408.7 / 162.9

THIS iteration (5) actually observed:
- passrate: 0.39  (over 100 tasks)
- failure clusters: {"correct": 39, "empty": 3, "unknown": 48, "wrong": 10}
- avg prompt/completion tokens: 1318.9 / 149.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.14814814814814814, "average_score": 0.14814814814814814}, "single-session-assistant": {"count": 11, "passrate": 0.8181818181818182, "average_score": 0.8181818181818182}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.07692307692307693, "average_score": 0.07692307692307693}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter005_structure_preserving_adaptive_context_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter004_query_focused_semantic_compression_top8.json

---
# PREDICTION TO SCORE

# iter_005 prediction

## Candidate
structure_preserving_adaptive_context

## Mechanism
Replace iter_004's fixed 4-sentence semantic compression with structure-aware adaptive context assembly, layered on the same calibrated retrieval stack (score-normalized RRF, compact formatting, 512-token generation budget).

1. **List-atomic compression**: Detect numbered/bullet lists within hits. When any list item is query-relevant, preserve the entire list block rather than compressing it to a fixed sentence count. This directly targets the two iter_004 regressions (3249768e cocktail list, 8cf51dda grant objectives) where answers were truncated away.

2. **Dynamic relevance-weighted budgets**: Allocate sentences per hit proportionally to its score (high >=0.95 gets up to 8, medium >=0.85 gets up to 5, low gets up to 3). This preserves more signal from top hits while trimming noise from tail hits.

3. **Archival list preservation**: Turn truncation in memgpt_scaffold.py becomes list-aware and the char limit rises from 300 to 500, recovering answers that live inside truncated list turns.

4. **Softer abstention prompt**: "If the context is insufficient, answer unknown" replaces the stricter "If the context does not contain the answer, say unknown", reducing over-abstention when evidence is present but scattered.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (from iter_004's 0.49 baseline to ~0.52–0.56)
- Failure type movement:
  - "unknown" cluster shrinks by 3–6 (the two list regressions convert, plus 1–4 additional synthesis failures where the softer prompt or preserved lists provide enough signal)
  - "empty" cluster stable or shrinks by 1–2 (512-token budget is already in place; no new budget change)
  - "wrong_answer" cluster stable (~7 tasks); the mechanism does not introduce new reasoning paths that would increase hallucination
- Trace movement:
  - Context blocks for top-scoring hits become longer when they contain lists (up to 8 sentences vs fixed 4)
  - Low-scoring tail hits become shorter (3 sentences vs fixed 4), slightly compressing noise
  - Predictions for list questions more often contain exact numbered/bulleted items from context
- Side effects to watch:
  - Prompt tokens may rise slightly because preserved list blocks are longer than 4-sentence summaries
  - Risk of 1–2 regressions if a preserved list block crowds out a different hit that contained the answer for an edge-case task
  - The 500-char archival limit (up from 300) increases average hit length; context budget pressure is the main countervailing force

## Falsification
- Passrate below 0.51 would mean the list-preservation heuristic fails to recover the known regressions or causes more damage via context crowding than it fixes.
- Passrate above 0.58 would imply the mechanism is unexpectedly effective at converting genuine retrieval misses, which is unlikely since retrieval ranking itself is unchanged from iter_004.
- 3249768e or 8cf51dda still failing would indicate the list-block detection or dynamic budget is not triggering correctly on the exact cases it was designed for.
- Empty predictions increasing would suggest the longer prompts from preserved lists are triggering Qwen3 hidden-thinking truncation, though the 512-token ceiling should contain this risk.

