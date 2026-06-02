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
# GROUND TRUTH for iteration 18

Previous iteration (17) observed:
- passrate: 0.17
- failure clusters: {"correct": 17, "empty": 0, "unknown": 81, "wrong": 2}
- avg prompt/completion tokens: 916.0 / 107.2

THIS iteration (18) actually observed:
- passrate: 0.64  (over 100 tasks)
- failure clusters: {"correct": 64, "empty": 3, "unknown": 23, "wrong": 10}
- avg prompt/completion tokens: 1558.5 / 224.2
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.9090909090909091, "average_score": 0.9090909090909091}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.9411764705882353, "average_score": 0.9411764705882353}, "temporal-reasoning": {"count": 26, "passrate": 0.5769230769230769, "average_score": 0.5769230769230769}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter018_contiguous_list_block_preservation_top8_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter017_abstention_retry_with_broader_retrieval_top8.json

---
# PREDICTION TO SCORE

# iter_018 prediction

## Candidate
contiguous_list_block_preservation

## Mechanism
Iter_017 catastrophically regressed from 0.69 to 0.17 because it applied the abstention-retry mechanism on top of the clean source snapshot without re-applying iter_016's load-bearing retrieval improvements (multi-granularity indexing, multi-signal fusion, adaptive limits, sentence compression, 1024-token budget). This candidate first restores the full iter_016 proven stack, then replaces the brittle ratio-based list-preservation heuristic (`list_markers >= len(units) * 0.5`) with contiguous list-block detection. The ratio-based approach fails when background prose dilutes the list ratio below 50%, causing structured answers (numbered objectives, bottle lists, DIY steps) to be compressed and reordered, destroying the structure the model needs. Contiguous-block detection looks for runs of 2+ consecutive list-marker lines and preserves the complete hit whenever such a block exists and the total unit count is reasonable (≤12). This is more robust because it depends on local structural contiguity, not global statistics, so embedding prose cannot hide a list block.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.05] (to ~0.71–0.74)
- Failure type movement: The list-truncation regression cluster (8cf51dda, 3249768e, 8aef76bc) should shrink from ~3 failures to ~0–1. The unknown/abstain cluster should stay flat or shrink by 1–2 if list-preservation also fixes synthesis failures on other list questions. Wrong answers should stay flat (~6). Empty predictions should stay at ~1.
- Trace movement: For previously failed list questions, the retrieved context should show complete list blocks instead of truncated/reordered sentences. No change in prompt length or format.
- Side effects to watch: Preserving complete list blocks in a few hits could consume slightly more context budget, potentially pushing out 1–2 tail hits for some tasks. The 8000-char limit and sliding-scale compression (5/3/2 sentences) should absorb this without major regressions.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or some other load-bearing component was lost in the patch application.
- If wrong-answer count rises, the list preservation is bringing in noisy/conflicting list content from lower-relevance hits.
- If empty predictions increase, the patch application inadvertently altered the prompt or model parameters (max_tokens, reasoning fallback).

