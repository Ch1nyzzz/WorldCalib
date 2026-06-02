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
# GROUND TRUTH for iteration 8

Previous iteration (7) observed:
- passrate: None
- failure clusters: null
- avg prompt/completion tokens: None / None

THIS iteration (8) actually observed:
- passrate: 0.53  (over 100 tasks)
- failure clusters: {"correct": 53, "empty": 11, "unknown": 26, "wrong": 10}
- avg prompt/completion tokens: 1588.1 / 205.4
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8235294117647058, "average_score": 0.8235294117647058}, "temporal-reasoning": {"count": 26, "passrate": 0.3076923076923077, "average_score": 0.3076923076923077}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter008_keyword_augmented_dual_pass_retrieval_top8.json
- previous candidate_results: None

---
# PREDICTION TO SCORE

# iter_008 prediction

## Candidate
keyword_augmented_dual_pass_retrieval

## Mechanism
Restore the iter_006 scaffold stack (compact formatting, score calibration, contiguous window compression, 512-token generation budget, reasoning_content fallback) and add three mechanisms on top: (1) keyword-augmented dual-pass retrieval — for each tier, run the hybrid ranker once with the full query and once with stopwords removed, then fuse with RRF — to reduce stopword dilution and surface docs that match content words but not full phrasing; (2) focal sentence highlighting (wrapping the peak-relevance sentence in `** **` inside each compressed hit) to increase salience of answer-bearing regions; (3) a softened system prompt that explicitly permits synthesis across passages and restricts abstention to cases where no relevant information is present.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.07] (from iter_006 baseline of 0.50, so predicted passrate ~0.52–0.57)
- Failure type movement: The unknown/abstain cluster should shrink modestly (3–7 tasks) because dual-pass retrieval recovers some gold-bearing docs that the full-query ranking missed, and the softer prompt reduces unnecessary abstention when evidence is present. The wrong-answer cluster may grow slightly (+1 to +3 tasks) because the more permissive synthesis instruction increases the risk of hallucination or over-aggregation on tasks with conflicting or incomplete evidence. The empty-prediction cluster may grow by 1–3 tasks because `** **` highlighting has been observed to trigger hidden thinking in Qwen3, consuming generation budget.
- Trace movement: Retrieval traces should show additional docs surfacing in the top-8 that were previously outside the pool, particularly for queries with heavy stopword load (e.g., personal pronouns, auxiliary verbs). Context traces should show `** ... **` markers around peak sentences in compressed hits. Completion traces for some tasks may show empty content with reasoning_content fallback activated.
- Side effects to watch: (a) Tier sort changed from `(priority, score)` to `(score, priority)` — this may demote core memory on tasks where it is the primary evidence source, causing regressions. (b) The `**` highlighting interacts with Qwen3's chat template; even with the 512-token budget and reasoning_content fallback, hidden thinking could still truncate the visible answer. (c) Prompt softening risks converting previously-abstained tasks into wrong answers rather than correct ones.

## Falsification
- If train passrate drops below 0.50, the mechanism is net harmful. The most likely culprits would be the `**` highlighting triggering hidden-thinking truncation, or the tier-sort change demoting core memory, or the prompt softening causing synthesis errors on tasks that iter_006 passed.
- If the unknown cluster does not shrink (i.e., the number of "unknown" predictions stays at ~32), then dual-pass retrieval is not effective at recovering missed gold docs on this split, and the primary failure family remains unaddressed.
- If the empty-prediction cluster grows by more than 3 tasks, then `**` highlighting is a stronger negative lever for Qwen3 than the reasoning_content fallback can compensate for.
- If the wrong-answer cluster grows by more than 3 tasks, the softer prompt is causing harmful hallucination/aggregation errors that outweigh its abstention-reduction benefit.

