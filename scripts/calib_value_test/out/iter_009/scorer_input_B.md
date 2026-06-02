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
The candidate layers two changes on top of iter_008's proven dual-pass retrieval, score calibration, and formatting: (1) a simplified direct-answer prompt that explicitly forbids step-by-step reasoning, reducing hidden thinking that consumes the 512-token completion budget; and (2) cross-hit evidence distillation that scores every sentence in every retrieved hit by cosine similarity to the query, extracts the top-N highest-scoring sentences across all hits, and presents them as "Relevant excerpts" at the very top of the prompt with inline provenance. The full compressed hits follow below.

This directly targets iter_008's two dominant failure families: empty/truncated outputs (10 tasks where Qwen3 consumed the completion budget in hidden thinking) and synthesis failures (a subset of the 21 unknown/abstain tasks where the answer was present in retrieved docs but buried or scattered across long passages). Front-loading the strongest evidence reduces cognitive load and makes it harder for the model to miss answer-bearing content, while the concise prompt should recover completion tokens currently lost to reasoning.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.09] (to ~0.57–0.62)
- Failure type movement: The empty/truncated-output cluster should shrink from ~10 tasks to 3–5 as the simplified prompt reduces hidden thinking. The unknown/abstain cluster should shrink modestly from ~21 tasks to 15–18 as distillation surfaces buried evidence in synthesis-failure cases. Retrieval-miss failures should stay flat. Wrong-answer count should stay flat at ~7 or rise by 1–2 as more aggressive synthesis occasionally misfires.
- Trace movement: Prompt traces should show noticeably shorter system/user instructions and a new "Relevant excerpts:" block at the top of the context. Completion tokens should drop for previously empty tasks. Spans should show inline provenance markers linking excerpts to their source hits.
- Side effects to watch: Prompt token consumption may rise slightly because excerpts are added on top of full hits, potentially crowding out the lowest-ranked hit for some tasks. Risk of regressions on tasks where the answer requires cross-sentence context that gets fragmented by per-sentence extraction (e.g., temporal reasoning across multiple turns).

## Falsification
- If passrate does not improve or regresses, the simplified prompt did not reduce hidden thinking enough to offset any noise added by distillation, or the 512-token ceiling is a hard bottleneck that prompt changes cannot bypass.
- If the empty cluster stays at ~10 despite the simplified prompt, Qwen3 hidden thinking is driven by something other than prompt verbosity (e.g., a serving-layer behavior that ignores chat_template_kwargs).
- If wrong-answer count rises by more than 2, sentence-level extraction is stripping contextual guardrails and causing the model to synthesize incorrect answers from isolated excerpts.
- If prompt token consumption rises by more than ~150 tokens on average, the added excerpts are consuming context budget and displacing load-bearing hits.

