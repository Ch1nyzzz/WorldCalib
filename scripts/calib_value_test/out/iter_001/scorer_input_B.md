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
Compress retrieved hits through compact archival/recall formatting, per-hit truncation (max_hit_chars=1200), shorter per-turn archival building (300 chars), and a simplified core-memory representation. Strengthen the answer prompt to explicitly instruct the model to read all passages before answering unknown. Additionally, sort deduplicated hits by score first rather than tier first, so higher-scoring evidence is retained in the limited context window.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.18] to ~0.26–0.34
- Failure type movement: The dominant "unknown/abstain" cluster should shrink significantly (from ~81 to ~50–60 tasks) as more evidence becomes visible and the prompt reduces conservative abstention. The retrieval-miss cluster stays roughly flat at ~40 tasks. Wrong answers should increase modestly from ~2 to ~5–10 as the model answers more aggressively.
- Trace movement: Context spans should show 5–7 hits in the prompt instead of the baseline 2–3. Predictions should contain fewer verbatim "unknown" outputs and more direct answers.
- Side effects to watch: Completion-token counts may rise slightly due to longer reasoning before FINAL ANSWER, but empty/truncated outputs should remain rare (<5 tasks) because the prompt is only moderately more verbose. A small number of tasks may regress if score-first sorting demotes a previously load-bearing core/summary hit, though core memory rarely contains specific answers.

## Falsification
- If train passrate Δ is below +0.05, the mechanism failed: either compression did not bring gold-bearing docs into the visible context, or the prompt change did not reduce abstention.
- If empty predictions spike above 10, the prompt is triggering Qwen3 hidden-thinking truncation despite its moderate length.
- If wrong answers grow above 15, the directive prompt is too permissive and causing hallucinations.
- If the passrate regresses vs baseline (0.16), the tier-sort-key change or per-turn archival truncation is actively destroying answer-bearing evidence.

