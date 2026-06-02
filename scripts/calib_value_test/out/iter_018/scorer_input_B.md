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
Iter_017 catastrophically regressed from 0.69 to 0.17 by building the abstention-retry mechanism on the clean source snapshot without re-applying iter_016's load-bearing retrieval improvements. This candidate first restores the full iter_016 proven stack (multi-granularity archival indexing, multi-signal hybrid ranking with bigram/char-ngram fusion, RRF-based ranking fusion, adaptive retrieval limits, sentence-level relevance surfacing, 1024-token generation budget, reasoning-content fallback), then replaces the brittle ratio-based list-preservation heuristic (`list_markers >= len(units) * 0.5`) with contiguous list-block detection. The new rule looks for runs of 2+ consecutive list-marker lines and preserves the complete hit without truncation or reordering whenever such a block exists and the total unit count is ≤12. This is more robust because it depends on local structural contiguity rather than global statistics, so embedding prose cannot hide a list block.

## Outcome prediction
- Train passrate Δ: [+0.50, +0.54] from iter_017's 0.17, to an absolute ~0.67–0.71. The central estimate is ~0.70 (restoring iter_016's 69 passes and recovering the one known regression 8cf51dda).
- Failure type movement: The persistent_fail cluster should collapse from ~83 tasks (iter_017) back to ~30 tasks (iter_016 level) as the retrieval stack is restored. The unknown/abstain cluster should shrink by ~1 task (8cf51dda moving from unknown to correct). Wrong-answer and empty-output clusters should remain stable at iter_016 levels (~6 wrong, ~1 empty).
- Trace movement: Retrieval scores for top hits should return to iter_016 levels (0.90+ cosine for relevant docs) instead of iter_017's broken retrieval (0.03–0.30). Prompt token counts should return to iter_016's range (~1400–1800 tokens). 8cf51dda should appear as a stable_pass or breakthrough instead of a regression.
- Side effects to watch: (1) The contiguous-block heuristic is slightly more permissive than the ratio heuristic for small embedded lists in long prose, which could increase average prompt length by 0–5% but should not blow the context budget because the condition is bounded (≤12 units). (2) If the restoration missed any load-bearing component from iter_016, the passrate could land below 0.65. (3) No Qwen3 empty-output spike is expected because the prompt and generation path are unchanged from iter_016.

## Falsification
- If train passrate is <0.65, the iter_016 stack restoration was incomplete or the list-block change introduced unexpected regressions.
- If 8cf51dda does NOT pass, the contiguous-block detection failed to preserve the objectives list or the retrieval stack was not fully restored.
- If empty predictions jump above 2 (iter_016 had ~1), the generation path was altered in a way that triggers Qwen3 hidden thinking.
- If wrong-answer count grows beyond iter_016's ~6, the list-block preservation is surfacing noisy or irrelevant structured content that confuses synthesis.

