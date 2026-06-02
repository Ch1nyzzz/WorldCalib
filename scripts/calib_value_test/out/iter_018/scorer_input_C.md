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
Restore the full iter_016 proven retrieval stack (multi-granularity indexing, multi-signal fusion, adaptive limits, sentence compression, 1024-token budget) and replace the brittle ratio-based list-preservation heuristic in `_compress_hit` with contiguous list-block detection. The ratio heuristic (`list_markers >= len(units) * 0.5`) fails when background prose dilutes the list ratio below 50%, causing structured answers to be compressed and reordered. The new mechanism looks for runs of 2+ consecutive list-marker lines and preserves the complete hit whenever such a block exists and total units are ≤12. This is a local-structure cue that is insensitive to global prose dilution.

## Outcome prediction
- Train passrate Δ: [+0.52, +0.54] from iter_017 (absolute ~0.69–0.71)
- Failure type movement: The catastrophic unknown/abstain cluster that dominated iter_017 (83 persistent fails) should collapse back to roughly iter_016 levels (~30 persistent fails) because the load-bearing retrieval infrastructure is restored. The list-related partial-answer regression `8cf51dda` (grant objectives — model found 2 of 3 in iter_016, 0 of 3 in iter_015) should flip from fail to pass, shrinking the partial-answer/wrong-answer cluster by 1.
- Trace movement: For `8cf51dda`, the prediction should contain all three grant objectives in order rather than omitting the first. For the majority of previously-failed tasks, traces should resemble iter_016: evidence is retrieved and the model either synthesizes a concrete answer or abstains based on coverage, rather than uniformly abstaining due to missing retrieval.
- Side effects to watch: Average token consumption should jump from iter_017's ~1,023 back toward iter_016's ~1,807 because the full retrieval stack is restored. The list-block preservation may add a small additional token bump on hits with short list blocks, but the ≤12-unit cap limits it. Risk of regression on non-list tasks is low because the change is scoped to `_compress_hit` and only activates on contiguous list blocks.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or the source snapshot diverges from iter_016 in some load-bearing way.
- If passrate recovers to exactly 0.69 but not higher, the list-block fix did not save `8cf51dda` (likely because the source memory text is already truncated before `_compress_hit` runs, or because the model still fails to synthesize even when the full list is visible).
- If passrate exceeds 0.72, there were more list-block compression failures hidden in the persistent-fail set than the one known regression, and the contiguous-block mechanism saved additional tasks.
- If wrong-answer count rises relative to iter_016, preserving complete list hits with surrounding prose is introducing distracting context that pushes the model to hallucinate or mis-aggregate.

