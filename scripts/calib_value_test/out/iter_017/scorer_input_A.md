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
The dominant remaining failure family is unknown/abstain (~18/25 failures in iter_016). This cluster splits into two sub-families:
1. Synthesis failures where evidence is present but the model abstains conservatively. Two independent evidence sources: (a) gpt4_2f91af09 — the retrieved docs explicitly mention "17 poems", "five short stories", and "one writing challenge piece", yet the model refuses to aggregate them into 23; (b) 8cf51dda — the top retrieved doc contains all three grant objectives in a numbered list, yet the model claims only two are present.
2. Partial retrieval misses where the initial top-8 pool contains some evidence but misses supporting docs. Evidence: 129d1232 finds $5,000 + $250 but gold is $5,850, indicating other charity event docs are missing; 60036106 finds Facebook 2,000 reach but misses the Instagram influencer doc needed for the 12,000 total.

The new mechanism is an abstention-triggered retry: after the first retrieval-and-synthesis pass, if the model outputs "unknown", an empty string, or a clear abstention phrase, a second pass is triggered with (a) a doubled retrieval pool (top_k=16 archival + 16 recall) to increase coverage, and (b) a slightly more directive synthesis prompt that explicitly instructs the model to combine information across passages. The retry only fires on abstention, so already-passing tasks are unaffected. The 1024-token generation budget and minimal prompt are kept as load-bearing infrastructure.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.06] (to ~0.72–0.75)
- Failure type movement: Unknown/abstain cluster should shrink by 3–5 tasks (synthesis failures where the directive prompt helps, plus partial retrieval misses where the broader pool brings in the missing doc). Wrong answers should stay flat or rise by at most 1 (risk of hallucination from noisy broader retrieval). Empty predictions should stay at ~1.
- Trace movement: For previously failed synthesis tasks, the second-pass prediction should be a concrete answer rather than "unknown". For partial retrieval misses, the second retrieval should surface additional hits not present in the first pass.
- Side effects to watch: Token consumption rises ~20–25% because ~25% of tasks trigger a second model call. Risk of timeout if the second call is slow. Risk of regression on genuinely-unanswerable tasks if the broader retrieval brings in conflicting noise and the directive prompt pushes the model to hallucinate.

## Falsification
- If passrate does not improve or regresses, the unknown cluster is dominated by genuine retrieval misses where the broader pool still does not contain the gold doc, or the directive prompt causes hallucinations on ambiguous tasks.
- If wrong-answer count rises by more than 1, the broader retrieval is adding noisy/conflicting docs that the directive prompt overweights.
- If empty predictions increase, the second prompt is triggering Qwen3 hidden thinking.

