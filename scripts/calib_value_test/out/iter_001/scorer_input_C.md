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
# GROUND TRUTH for iteration 1

Previous iteration (0) observed:
- passrate: None
- failure clusters: null
- avg prompt/completion tokens: None / None

THIS iteration (1) actually observed:
- passrate: 0.38  (over 100 tasks)
- failure clusters: {"correct": 38, "empty": 25, "unknown": 33, "wrong": 4}
- avg prompt/completion tokens: 1637.5 / 168.6
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.6, "average_score": 0.6}, "multi-session": {"count": 27, "passrate": 0.18518518518518517, "average_score": 0.18518518518518517}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.11538461538461539, "average_score": 0.11538461538461539}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter001_memgpt_compact_context_top10.json
- previous candidate_results: None

---
# PREDICTION TO SCORE

# iter_001 prediction
## Candidate
memgpt_source_compact_context

## Mechanism
Compress retrieved hit formatting (more compact core/archival/recall rendering, per-hit truncation in context packing) and strengthen the answer prompt to explicitly instruct the model to search all passages before answering unknown.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.25]         (baseline 0.16 → expected 0.26–0.41)
- Failure type movement: The dominant failure cluster — "unknown" answers when evidence is present in retrieved hits — should shrink by 30–50%. Context-truncation failures (where the answer sits in lower-ranked hits dropped by the old all-or-nothing cutoff) should nearly disappear. Pure retrieval-miss failures will persist unchanged.
- Trace movement: Average prompt tokens should rise from ~900 to ~1,500–2,500 because far more hits fit into the 6,000-char budget. Fewer traces will end with "FINAL ANSWER: unknown"; more will show quoted context snippets before the final answer. The number of hits visible in the context span should increase from ~2–3 to ~8–12.
- Side effects to watch: Token consumption will grow modestly but should stay well below context limits. The explicit "quote the relevant part" wording could occasionally produce verbose answers, though the preserved "FINAL ANSWER: <answer>" guard should keep judge extraction stable. The switch from tier-priority to score-priority deduplication sorting is unlikely to regress already-correct tasks because high-scoring archival/recall hits are typically the answer-bearing ones.

## Falsification
- If passrate stays below 0.22, the mechanism is weaker than expected — likely because retrieval misses (not context truncation) are the primary bottleneck, or the prompt change is insufficient to overcome the model's conservatism.
- If the "unknown" rate does not drop below 60%, the prompt strengthening failed to change generation behavior.
- If average prompt tokens does not increase by at least 300, the compression did not meaningfully expand context coverage.

