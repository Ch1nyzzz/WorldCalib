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
After the first retrieval-and-synthesis pass, if the model abstains (outputs "unknown", empty string, or phrases like "does not contain"), a second pass is triggered with doubled retrieval pool (top_k=16) and a directive synthesis prompt instructing the model to combine information across passages. The retry only fires on abstention, so already-passing tasks are unaffected.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.05] (to ~0.71–0.74)
- Failure type movement: Unknown/abstain cluster should shrink by 2–4 tasks. The dominant sub-families are (1) synthesis failures where evidence is present but the model refuses to aggregate (e.g., 8cf51dda with three grant objectives, gpt4_2f91af09 with poem/story counts) and (2) partial retrieval misses where supporting docs sit just outside the top-8 pool (e.g., 60036106 missing Instagram reach). Wrong-answer count should stay flat because most wrong fails do not trigger the abstention detector.
- Trace movement: Retry traces should appear for ~20–25% of tasks (the 22/100 that abstained in iter_016). For the 2–4 tasks expected to convert, the retry trace will show a concrete answer replacing "unknown".
- Side effects to watch: Average token consumption per task should rise ~15–25% because abstaining tasks issue a second LLM call with a larger prompt. No pass regressions are expected since the retry only fires on abstention patterns that already produced fails.

## Falsification
- If passrate does not improve or regresses: the extra_instruction is too weak to overcome conservative abstention, or the max_context_chars=6000 limit renders the doubled retrieval pool ineffective (additional hits are truncated before reaching the model).
- If the unknown/abstain cluster does not shrink: the abstaining tasks are dominated by genuine retrieval misses rather than synthesis failures, so broader retrieval and directive prompting cannot help.
- If token consumption does not rise significantly: fewer tasks are hitting the abstention trigger than iter_016 suggested, or the retry logic is bypassed.
- If wrong-answer count rises: the directive to "combine information across passages" is causing hallucination on the retry pass for tasks with weak or ambiguous evidence.

