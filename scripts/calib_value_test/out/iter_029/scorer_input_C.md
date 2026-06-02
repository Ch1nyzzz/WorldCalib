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
Restore the proven iter_027 stack (multi-signal retrieval, MMR diversity reranking, 2048-token generation budget, sentence compression, adjacent archival hit merging) and add temporal date-aware boosting: after multi-signal fusion and before MMR selection, docs whose dates match literal month names or 4-digit years in the query receive a small relevance boost (+0.10 for month, +0.05 for year).

## Outcome prediction
- Train passrate Δ: [+0.02, +0.03] from 0.68 to ~0.70–0.71
- Failure type movement: The three iter_028 regressions (ba61f0b9, c4ea545c, f8c5f88b) should flip back to passing because the source reverts to the proven iter_027 stack. No additional persistent-fail tasks should be resolved because temporal boosting is extremely narrow: only three queries contain literal month names (10d9b85a, 80ec1f4f_abs, 5809eb10), and 10d9b85a has no April-dated docs in its retrieval pool while the other two already pass.
- Trace movement: Traces for the three regression tasks should show the same retrieval patterns as iter_027 and completions should return to their iter_027 forms (detailed answer for c4ea545c, "6 women" for ba61f0b9, "From a sports store downtown" for f8c5f88b). Traces for month-containing queries may show score bumps on date-matching docs but no material reordering because either no docs match (10d9b85a) or all top docs match uniformly (5809eb10).
- Side effects to watch: Token consumption should stay flat relative to iter_027 (~1830 avg). No empty-output regression because the 2048-token budget and reasoning_content fallback are preserved. No new wrong-answer regressions expected because the boost only affects ranking for a tiny fraction of queries and does not inject answer information.

## Falsification
- Passrate stays at or below 0.69 (would refute the hypothesis that restoring the iter_027 stack reliably recovers the three known regressions).
- Any new task fails that passed in both iter_027 and iter_028 (would indicate an unanticipated side effect from temporal boost or from the tiny regex fix in model.py).
- Wrong-answer count rises by >1 (would indicate temporal boost is surfacing contradictory docs for the month-matched queries).

