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
# GROUND TRUTH for iteration 29

Previous iteration (28) observed:
- passrate: 0.68
- failure clusters: {"correct": 68, "empty": 0, "unknown": 17, "wrong": 15}
- avg prompt/completion tokens: 1607.1 / 201.8

THIS iteration (29) actually observed:
- passrate: 0.11  (over 100 tasks)
- failure clusters: {"correct": 11, "empty": 81, "unknown": 7, "wrong": 1}
- avg prompt/completion tokens: 295.7 / 28.8
- per-type score_breakdown: {"all": {"count": 81, "passrate": 0.0, "average_score": 0.0}, "knowledge-update": {"count": 2, "passrate": 1.0, "average_score": 1.0}, "multi-session": {"count": 5, "passrate": 0.2, "average_score": 0.2}, "single-session-assistant": {"count": 4, "passrate": 1.0, "average_score": 1.0}, "single-session-user": {"count": 1, "passrate": 1.0, "average_score": 1.0}, "temporal-reasoning": {"count": 7, "passrate": 0.42857142857142855, "average_score": 0.42857142857142855}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter029_temporal_date_boost_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter028_answer_type_boost_aggregation_top8.json

---
# PREDICTION TO SCORE

# iter_029 prediction

## Candidate
temporal_date_boost

## Mechanism
Restore the proven iter_027 stack (multi-signal retrieval, MMR diversity reranking, 2048-token generation budget, sentence compression, adjacent archival hit merging) and add a single new retrieval-side mechanism: temporal date-aware boosting. After multi-signal fusion and before MMR selection, docs whose dates match temporal expressions in the query (month names, years) receive a small relevance boost. This targets retrieval misses where the query references a specific time period but semantically similar docs from other periods outrank the gold docs (e.g., 10d9b85a where May docs outranked April docs for an April query).

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from 0.71 to ~0.72–0.74
- Failure type movement: The retrieval-miss cluster should shrink by 2–4 tasks, especially temporal-mismatch cases (10d9b85a, possibly 129d1232). The unknown cluster should drop slightly. Wrong-answer count should stay flat or drop by 1.
- Trace movement: Diagnostic traces for temporal queries should show top hits from the correct month/year. No change in prompt length or completion patterns.
- Side effects to watch: Token consumption should stay flat (retrieval-tier only). No risk of empty outputs because prompt is unchanged. Risk of query drift if a query mentions a date in a non-temporal sense (e.g., "What did I do before April?"); the small boost magnitude (0.10 for month, 0.05 for year) should not overwhelm strong lexical matches.

## Falsification
- Passrate stays flat or drops below 0.71 (would refute the hypothesis that temporal boosting improves retrieval coverage).
- Wrong-answer count rises by >2 (would indicate the boost is surfacing contradictory or noisy docs from the wrong period).
- Empty outputs reappear (would indicate an unintended prompt change; but this candidate does not touch the prompt).

