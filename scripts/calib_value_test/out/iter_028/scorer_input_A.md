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
# GROUND TRUTH for iteration 28

Previous iteration (27) observed:
- passrate: 0.71
- failure clusters: {"correct": 71, "empty": 0, "unknown": 21, "wrong": 8}
- avg prompt/completion tokens: 1594.3 / 236.4

THIS iteration (28) actually observed:
- passrate: 0.68  (over 100 tasks)
- failure clusters: {"correct": 68, "empty": 0, "unknown": 17, "wrong": 15}
- avg prompt/completion tokens: 1607.1 / 201.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.5185185185185185, "average_score": 0.5185185185185185}, "single-session-assistant": {"count": 11, "passrate": 1.0, "average_score": 1.0}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8823529411764706, "average_score": 0.8823529411764706}, "temporal-reasoning": {"count": 26, "passrate": 0.6153846153846154, "average_score": 0.6153846153846154}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter028_answer_type_boost_aggregation_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter027_mmr_diversity_rerank_2048_top8.json

---
# PREDICTION TO SCORE

# iter_028 prediction

## Candidate
answer_type_boost_aggregation

## Mechanism
Add answer-type-aware boosting to the retrieval ranking and adaptive MMR/synthesis for aggregation queries.

1. **Retrieval boosting**: After multi-signal fusion, docs that contain the expected answer type (numbers for "how much/many", dates for "when/how long", yes/no for boolean queries, list markers for enumeration queries) receive a small score boost. This helps surface evidence that is semantically relevant but lexically mismatched.

2. **Adaptive MMR for aggregation**: When aggregation signals are detected ("total", "all", "how many", "sum", "combined", "every", "each", "list"), the MMR candidate pool expands from k*3 to k*4 and lambda drops from 0.9 to 0.8, trading a small amount of relevance for more diversity. This brings scattered evidence into the context window.

3. **Aggregation synthesis hint**: For aggregation queries, the system prompt includes a one-line note: "When the question asks for a total, count, or list, carefully review all retrieved entries and combine the relevant facts before answering." This directly addresses synthesis failures where evidence is present but the model only uses a subset.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from 0.71 to ~0.72–0.74
- Failure type movement: The partial-aggregation/wrong-answer cluster (10d9b85a, a08a253f, 852ce960, gpt4_2f91af09) should shrink by 2–4 tasks. The retrieval-miss cluster may also shrink slightly if answer-type boosting surfaces previously buried docs (129d1232, a08a253f). Unknown cluster should stay flat or shrink by 1–2.
- Trace movement: Diagnostic traces for aggregation tasks should show more diverse top-hit content. Model completions for aggregation tasks should show explicit combining language ("and", "total", "altogether").
- Side effects to watch: Token consumption may rise modestly because aggregation queries will see slightly more hits in context (pool expansion but same final k). Wrong-answer count should not rise because the boost only affects ranking, not answer injection. Empty outputs should remain at 0.

## Falsification
- Passrate stays flat or drops (would refute the hypothesis that answer-type boosting and aggregation tuning improve coverage/synthesis).
- Wrong-answer count rises by >2 (would indicate the boost is surfacing contradictory or noisy docs).
- Empty outputs reappear (would indicate the aggregation prompt instruction triggers Qwen3 hidden thinking).

