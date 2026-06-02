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
Restore the proven iter_027 stack (multi-signal retrieval, MMR diversity reranking, 2048-token generation budget, sentence compression, adjacent archival hit merging) and add temporal date-aware boosting: after multi-signal fusion and before MMR selection, docs whose dates match explicit month names (+0.10) or years (+0.05) in the query receive a small relevance boost.

## Outcome prediction
- Train passrate Δ: [+0.00, +0.02] from the iter_027 baseline of ~0.71, yielding an absolute passrate of ~0.71–0.73 (equivalently, +0.03 to +0.05 from iter_028's 0.68).
- Failure type movement: The persistent-fail count should stay flat or drop by at most 1 task. The dominant unknown/abstain cluster (~29 tasks) will not shrink meaningfully because temporal boosting only handles explicit month/year queries, and the primary target (10d9b85a "April") likely has no April-dated docs in the corpus — the April workshop evidence is embedded inside May-dated conversation turns, which doc-date boosting cannot surface. The wrong-answer cluster (~15 tasks) and empty-output cluster (0 tasks) should remain unchanged.
- Trace movement: Retrieval spans for queries containing month names (e.g., "April", "May") or 4-digit years should show slightly elevated scores for docs with matching dates. No new breakthrough patterns or aggregation-language changes should appear in model completions.
- Side effects to watch: Token consumption should remain comparable to iter_027 (~1830 avg). No new empty-output regressions expected because the prompt/model tier is unchanged. The small boost magnitude (+0.10) limits the risk of surfacing noisy or contradictory docs.

## Falsification
- Passrate drops below 0.70 (would indicate the iter_027 stack restoration is imperfect or the temporal boost introduces unexpected regressions).
- Passrate exceeds 0.73 (would mean temporal boosting is fixing more tasks than the narrow signal can plausibly reach).
- Wrong-answer count rises by >2 (would indicate the boost is promoting contradictory or semantically mismatched but temporally aligned docs).
- Empty outputs reappear (would indicate a hidden prompt or model-tier change not documented in the diff).

