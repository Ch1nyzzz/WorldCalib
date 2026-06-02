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
# GROUND TRUTH for iteration 17

Previous iteration (16) observed:
- passrate: 0.69
- failure clusters: {"correct": 69, "empty": 1, "unknown": 21, "wrong": 9}
- avg prompt/completion tokens: 1592.4 / 214.6

THIS iteration (17) actually observed:
- passrate: 0.17  (over 100 tasks)
- failure clusters: {"correct": 17, "empty": 0, "unknown": 81, "wrong": 2}
- avg prompt/completion tokens: 916.0 / 107.2
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.2, "average_score": 0.2}, "multi-session": {"count": 27, "passrate": 0.1111111111111111, "average_score": 0.1111111111111111}, "single-session-assistant": {"count": 11, "passrate": 0.6363636363636364, "average_score": 0.6363636363636364}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.17647058823529413, "average_score": 0.17647058823529413}, "temporal-reasoning": {"count": 26, "passrate": 0.038461538461538464, "average_score": 0.038461538461538464}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter017_abstention_retry_with_broader_retrieval_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter016_sentence_surfacing_with_structure_preservation_top8.json

---
# PREDICTION TO SCORE

# iter_017 prediction

## Candidate
abstention_retry_with_broader_retrieval

## Mechanism
After the first retrieval-and-synthesis pass, if the model abstains (empty prediction, exact "unknown", or text containing "insufficient" / "does not contain"), a second pass is triggered with doubled top_k (16 archival + 16 recall) and a slightly more directive synthesis prompt instructing cross-passage combination. The retry only fires on abstention, so already-passing tasks are unaffected. The 1024-token generation budget and 8000-character context limit are raised from the clean-snapshot defaults.

## Outcome prediction
- Train passrate Δ: [-0.34, -0.26] (to ~0.35–0.43)
- Failure type movement: The unknown/abstain cluster will grow sharply from ~18/25 to ~40–55/65–70 failures because the candidate rebuilds from the clean snapshot without restoring the proven score-calibrated, compact-formatted retrieval stack from iters 002–016. Empty predictions will shrink from ~1 to ~2–5 thanks to the 1024-token budget. Wrong answers will rise modestly to ~10–15 as the directive retry prompt occasionally pushes the model to synthesize across noisy or partial hits. The retry mechanism itself will convert only ~3–6 abstaining tasks because (a) the abstention detector is extremely narrow (it misses the common "unknown FINAL ANSWER: unknown" pattern), and (b) the clean snapshot’s uncalibrated retrieval often fails to rank gold-bearing docs into even the top-16 pool.
- Trace movement: Traces for abstaining tasks will show a second retrieval call with top_k=16 and a second LLM call carrying the extra_instruction. Most persistent failures will show gold docs ranked below the top-8 or entirely absent, with summary/core memory still dominating the hit list due to the uncalibrated +0.2/+0.1 score boosts.
- Side effects to watch: Average token consumption will rise by ~25–40% (not the predicted 20–25%) because poor retrieval produces more abstentions, triggering more second-pass LLM calls. Runtime per task will increase proportionally. A small number of previously-passing tasks could regress if their correct answer happens to contain the substring "insufficient" or "does not contain", causing an erroneous retry that introduces noise.

## Falsification
- If passrate is ≥0.55, the evaluation harness must be re-using a cached build or pre-loaded index from a previous iteration (e.g., iter_016’s memgpt_surfacing_v16) rather than rebuilding from the clean snapshot with tag memgpt_retry_v17, because the clean snapshot’s uncalibrated retrieval cannot support that passrate.
- If passrate is ≥0.65, the source snapshot must contain hidden retrieval improvements (score normalization, compact formatting, or sentence surfacing) that were not visible in the diff.
- If the empty-prediction cluster grows beyond 10 tasks, the 1024-token budget is not being applied (e.g., base.py still hardcodes 256 somewhere in the call chain).
- If wrong-answer count stays flat or shrinks despite the retry, the directive prompt is not actually increasing synthesis aggressiveness, or the retry is firing too rarely to matter.

