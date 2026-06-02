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
# GROUND TRUTH for iteration 12

Previous iteration (11) observed:
- passrate: 0.47
- failure clusters: {"correct": 47, "empty": 10, "unknown": 34, "wrong": 9}
- avg prompt/completion tokens: 1504.2 / 187.3

THIS iteration (12) actually observed:
- passrate: 0.57  (over 100 tasks)
- failure clusters: {"correct": 57, "empty": 2, "unknown": 33, "wrong": 8}
- avg prompt/completion tokens: 1460.7 / 233.4
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8666666666666667, "average_score": 0.8666666666666667}, "multi-session": {"count": 27, "passrate": 0.3333333333333333, "average_score": 0.3333333333333333}, "single-session-assistant": {"count": 11, "passrate": 0.6363636363636364, "average_score": 0.6363636363636364}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8823529411764706, "average_score": 0.8823529411764706}, "temporal-reasoning": {"count": 26, "passrate": 0.5, "average_score": 0.5}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter012_answer_signal_prioritized_two_tier_context_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter011_fixed_window_list_skeleton_highlighting_top8.json

---
# PREDICTION TO SCORE

# iter_012 prediction

## Candidate
answer_signal_prioritized_two_tier_context

## Mechanism
The candidate targets the dominant failure family from iter_011: Qwen3 hidden-thinking truncation causing empty predictions (10 tasks) and prompt-complexity-induced abstention (34 unknown/abstain). It replaces iter_011's list-skeleton + ** highlighting with:
1. **1024-token generation budget** — directly counters hidden-thinking truncation that produced empty outputs at the 512-token ceiling.
2. **Minimal prompt** — strips ** highlighting, list-preservation logic, and verbose instructions to avoid triggering Qwen3 reasoning mode.
3. **Answer-signal prioritization** — detects answer-type cues (number, date, list, yes/no) from the question and reorders retrieved hits so that hits containing matching cues appear first.
4. **Two-tier compression** — Tier-1 hits (top 2 or answer-signal hits) get minimal compression (up to 1000 chars) preserving the most promising evidence in full; Tier-2 hits get aggressive 3-sentence window compression to preserve context budget.

The retrieval foundation is explicitly preserved: dual-pass keyword retrieval, RRF normalization, score-first tier sorting, compact formatting, and reasoning_content fallback.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (from iter_011's 0.47 to ~0.50–0.54)
- Failure type movement: Empty predictions should drop from 10 to 3–5 (the 4 confirmed iter_010→iter_011 regressions — 60bf93ed, 85fa3a3f, gpt4_1916e0ea, gpt4_74aed68e — should recover, plus 1–2 additional empty fixes from the larger budget). Unknown/abstain should shrink by 2–4 tasks as Tier-1 minimal compression lets the model synthesize evidence that was previously truncated. Wrong-answer count should stay flat at ~9 or rise by at most 1.
- Trace movement: Empty-string predictions should decrease significantly; compressed hits should show fuller Tier-1 content (up to 1000 chars) and shorter Tier-2 snippets; no ** wrapping or list-skeleton artifacts in prompts.
- Side effects to watch: Token consumption will rise due to the 1024-token generation budget and larger Tier-1 hit budgets. Risk of regressions from aggressive 3-sentence Tier-2 truncation dropping disambiguating evidence, or from answer-signal misprioritization reordering truly relevant hits lower.

## Falsification
- If passrate does not improve or regresses, the 1024-token budget and minimal prompt did not fix Qwen3 hidden-thinking truncation, or the two-tier compression caused more regressions than the empty-prediction fixes it delivered.
- If empty predictions stay at ~10, the generation budget is not the binding constraint on Qwen3 output truncation, and the failure family is misdiagnosed.
- If unknown/abstain grows while empty drops, the minimal prompt is too permissive and the model is substituting empty outputs with conservative abstentions.

