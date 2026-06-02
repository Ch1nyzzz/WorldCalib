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
Add answer-type-aware boosting to retrieval ranking and adaptive MMR/synthesis for aggregation queries. After multi-signal fusion, docs containing the expected answer type (numbers for quantitative queries, dates for temporal queries, yes/no cues for boolean queries, list markers for enumeration queries) receive a small score boost. For aggregation queries detected by keyword phrases ("total", "how many", "how much", etc.), the MMR candidate pool expands from 3× to 4× and lambda drops from 0.9 to 0.8, trading a small amount of relevance for more diversity. The system prompt also gains a one-line synthesis hint for aggregation queries: "When the question asks for a total, count, or list, carefully review all retrieved entries and combine the relevant facts before answering."

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from 0.71 to ~0.72–0.74
- Failure type movement: The aggregation persistent-fail cluster (10d9b85a April workshops, 129d1232 charity total, and 1–2 others) should shrink as adaptive MMR surfaces scattered evidence and the synthesis prompt drives combination. Yes/no (0bc8ad93 museum friend) and recommendation (0edc2aef Miami hotel) persistent failures should remain stable. Numerical inference gaps (157a136e grandma age) should persist unless answer-type boosting serendipitously surfaces the missing fact.
- Trace movement: Retrieval traces for aggregation queries should show more heterogeneous top-hit content (different events/amounts/dates) compared to iter_027. Model completions for aggregation queries should increasingly contain explicit summation or enumeration language.
- Side effects to watch: Average token consumption should stay flat (~1830) because pool expansion is modest and the context budget is unchanged. Wrong-answer count should not rise by more than 1 because boosts are small and capped at 0.15.

## Falsification
- Passrate stays flat or drops (would indicate answer-type boosting either has no effect or actively surfaces misleading docs).
- The two clearest aggregation targets (10d9b85a and 129d1232) remain failed despite adaptive MMR and synthesis hint (would indicate the bottleneck is retrieval coverage or evidence missing from the corpus, not ranking/synthesis).
- Wrong-answer count rises by >2 (would indicate the lower MMR lambda for aggregation is injecting noise that confuses the model).

