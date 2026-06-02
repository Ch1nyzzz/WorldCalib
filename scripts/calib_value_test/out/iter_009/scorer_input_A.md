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
# GROUND TRUTH for iteration 9

Previous iteration (8) observed:
- passrate: 0.53
- failure clusters: {"correct": 53, "empty": 11, "unknown": 26, "wrong": 10}
- avg prompt/completion tokens: 1588.1 / 205.4

THIS iteration (9) actually observed:
- passrate: 0.54  (over 100 tasks)
- failure clusters: {"correct": 54, "empty": 8, "unknown": 32, "wrong": 6}
- avg prompt/completion tokens: 1523.6 / 166.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.7333333333333333, "average_score": 0.7333333333333333}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8823529411764706, "average_score": 0.8823529411764706}, "temporal-reasoning": {"count": 26, "passrate": 0.34615384615384615, "average_score": 0.34615384615384615}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter009_cross_hit_evidence_distillation_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter008_keyword_augmented_dual_pass_retrieval_top8.json

---
# PREDICTION TO SCORE

# iter_009 prediction

## Candidate
cross_hit_evidence_distillation

## Mechanism
The dominant failure families in iter_008 are (1) empty/truncated outputs caused by Qwen3 consuming the 512-token budget in hidden thinking, and (2) synthesis failures where the answer is present in retrieved docs but buried or scattered across long passages.

The new candidate layers two changes on top of the proven dual-pass retrieval, score calibration, and formatting from iter_008:

1. **Simplified direct-answer prompt**: Replace the verbose iter_008 prompt with a concise instruction that explicitly forbids step-by-step reasoning and demands an immediate answer. This reduces hidden thinking that consumes completion tokens.

2. **Cross-hit evidence distillation**: Before assembling the context, score every sentence in every retrieved hit by cosine similarity to the query. Extract the top-N highest-scoring sentences across all hits and present them as "Relevant excerpts" at the very top of the prompt, with inline provenance (which hit each sentence came from). The full compressed hits follow below. This front-loads the most answer-bearing evidence, reducing the cognitive load on the model and making it less likely to miss scattered facts or run out of tokens while reasoning.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.57–0.63)
- Failure type movement: The empty-prediction cluster should shrink from 10 to 2–4. The "unknown despite relevant docs" synthesis cluster should shrink because scattered evidence is surfaced prominently. Wrong-answer count should stay flat or rise slightly (risk of over-reliance on excerpts).
- Trace movement: Retrieved documents should show the same dual-query fusion. Spans should show a new "excerpts" section in the prompt with cross-hit provenance.
- Side effects to watch: Token consumption may rise slightly because we present both excerpts and full hits; completion tokens should drop because the model reasons less. Risk of regressions on tasks where full narrative flow matters more than individual sentences.

## Falsification
- If passrate does not improve or regresses, the cross-hit distillation may be adding noise rather than signal, or the simplified prompt may be too terse and cause more abstentions.
- If empty predictions stay at ~10, the issue is not prompt verbosity but a deeper serving-layer bug with Qwen3 thinking tokens, and the prompt change was ineffective.
- If the "unknown" cluster stays flat while empty predictions drop, the remaining unknowns are genuine retrieval misses and distillation cannot compensate.

