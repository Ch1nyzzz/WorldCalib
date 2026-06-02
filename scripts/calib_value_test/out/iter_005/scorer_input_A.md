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
Replace fixed 4-sentence per-hit compression with structure-aware adaptive context assembly.

1. **List-atomic compression**: Detect numbered/bullet lists within retrieved hits. When any list item is query-relevant, preserve the entire list block rather than compressing it to a fixed sentence count. This fixes regressions like 8cf51dda (grant objectives compressed away) and persistent failures like 3249768e (cocktail list truncated).

2. **Dynamic relevance-weighted sentence budgets**: Allocate sentences per hit proportionally to its relevance score instead of a flat 4-sentence cap. High-confidence hits (score > 0.95) get up to 8 sentences; medium-confidence hits get up to 5; low-confidence hits get up to 3. This preserves more signal from the hits most likely to contain the answer while still trimming noise from tail hits.

3. **Archival list preservation**: In memgpt_scaffold.py, make the 300-char turn truncation list-aware. If a turn contains a numbered or bulleted list, preserve the full list even if it exceeds the character limit. This recovers answers that live inside truncated list turns.

4. **Generation budget liberation**: Fix the hidden base.py max_tokens=256 hardcode to 512 (confirmed load-bearing from iter_004).

5. **Slightly softer abstention prompt**: Change "If the context does not contain the answer, say unknown" to "If the context is insufficient, answer unknown" to reduce over-abstention when evidence is present but scattered.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (from iter_004’s 0.49 baseline to ~0.53–0.59)
- Failure type movement:
  - "unknown/empty" cluster shrinks by 4–8 (structured answers now visible in context)
  - "wrong_answer" cluster stable or shrinks slightly (better evidence coverage)
  - Regressions from iter_002 eliminated (8cf51dda and similar list questions)
- Trace movement:
  - More predictions contain exact enumeration phrases ("1. To identify...", "5. Absinthe")
  - Completion tokens stable (512 budget already in use)
  - Prompt tokens may rise 5–15% on list-heavy tasks but stay within budget
- Side effects to watch:
  - Context budget exhaustion on queries with many long lists (mitigated by dynamic budgeting for low-relevance hits)
  - Risk of including irrelevant list items when a list is partially relevant

## Falsification
- Passrate below 0.50 would suggest list preservation adds noise or bloat that hurts more than it helps
- "unknown" cluster not shrinking would mean most failures are genuine retrieval misses, not compression artifacts
- Breakthroughs below 5 would indicate the mechanism lacks leverage on this split

