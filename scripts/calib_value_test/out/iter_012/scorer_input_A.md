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
The dominant failure family is Qwen3 hidden-thinking truncation causing empty predictions (~10 tasks in iter_011) and prompt-complexity-induced abstention. The iter_011 list-skeleton + ** highlighting mechanism made both worse by increasing prompt complexity and trigger tokens.

The new mechanism is a two-tier context packing strategy paired with a larger generation budget:
1. **Increase max_tokens to 1024** to give Qwen3 room to finish hidden thinking and still emit an answer.
2. **Answer-signal prioritization**: detect answer-type cues (number, date, list, yes/no) from the question; reorder retrieved hits so that hits containing matching cues appear first.
3. **Two-tier compression**: Tier-1 hits (top 2, or all answer-signal hits if fewer) get minimal compression (up to 1000 chars) so the model can read the most promising evidence in full. Tier-2 hits get aggressive 3-sentence window compression to preserve context budget.
4. **Minimal prompt**: strip all formatting triggers (** highlighting, list-preservation logic, verbose instructions) and use the simplest direct-answer instruction.

The retrieval foundation is kept load-bearing: dual-pass keyword retrieval, RRF score normalization, score-first tier sorting, compact core/hit formatting, 300-char archival truncation, and reasoning_content fallback.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.12] (to ~0.52–0.59)
- Failure type movement: Empty predictions should shrink from 10 to 2–4 (1024-token budget + simple prompt). Unknown/abstain should shrink by 3–6 tasks (top hits are less compressed, making evidence easier to spot). Wrong-answer count should stay flat or rise by 1.
- Trace movement: Compressed hits should no longer contain ** wrapping or list-skeleton artifacts. Top hits should be longer and more readable. Completion tokens should show a bimodal distribution: short (~50–150) for easy tasks, long (~500–800) for tasks where hidden thinking occurs but now has room to complete.
- Side effects to watch: Token consumption will rise because of 1024-token completions on some tasks and larger top-hit context. Risk of regressions on tasks where the answer is in a tier-2 hit that gets aggressively truncated by the 3-sentence window.

## Falsification
- If empty predictions do not shrink below 5, the 1024-token budget is insufficient or the prompt still triggers hidden thinking; a more aggressive prompt simplification or temperature change would be needed.
- If passrate does not improve or regresses, the two-tier truncation may be dropping critical evidence in tier-2 hits, or the answer-signal detection may be too noisy and demote the true gold hit.
- If the unknown cluster stays flat while empty predictions improve, the remaining unknowns are genuine retrieval misses and context packing cannot compensate.

