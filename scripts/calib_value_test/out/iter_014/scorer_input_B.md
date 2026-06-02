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
# GROUND TRUTH for iteration 14

Previous iteration (13) observed:
- passrate: 0.63
- failure clusters: {"correct": 63, "empty": 3, "unknown": 25, "wrong": 9}
- avg prompt/completion tokens: 1651.5 / 208.1

THIS iteration (14) actually observed:
- passrate: 0.66  (over 100 tasks)
- failure clusters: {"correct": 66, "empty": 4, "unknown": 18, "wrong": 12}
- avg prompt/completion tokens: 1656.4 / 238.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.9333333333333333, "average_score": 0.9333333333333333}, "multi-session": {"count": 27, "passrate": 0.5185185185185185, "average_score": 0.5185185185185185}, "single-session-assistant": {"count": 11, "passrate": 0.6363636363636364, "average_score": 0.6363636363636364}, "single-session-preference": {"count": 4, "passrate": 0.25, "average_score": 0.25}, "single-session-user": {"count": 17, "passrate": 0.9411764705882353, "average_score": 0.9411764705882353}, "temporal-reasoning": {"count": 26, "passrate": 0.5384615384615384, "average_score": 0.5384615384615384}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter014_list_atomic_compression_with_directive_prompt_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter013_multi_granularity_adaptive_retrieval_top8.json

---
# PREDICTION TO SCORE

# iter_014 prediction

## Candidate
list_atomic_compression_with_directive_prompt

## Mechanism
The candidate targets the synthesis failure family where evidence is present in retrieved hits but the model either abstains or extracts a truncated answer. It layers two bounded changes on top of the proven multi-granularity retrieval stack:

1. **List-atomic compression** (model.py): For top-2 hits containing 3+ list items, when the question asks for a list-related answer (detected by `_answer_type_patterns`), the per-hit compression budget expands from a fixed 5 sentences to `list_items + 2`. This preserves complete list blocks while still bounding per-hit length.
2. **Directive prompt tweak** (model.py): The system prompt shifts from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

Both changes are tightly scoped: list expansion applies only to the first two hits with clear list structure, and the prompt change is a wording shift without added reasoning instructions, so it should not trigger Qwen3 hidden thinking.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.05] (to ~0.64–0.68)
- Failure type movement:
  - Unknown/abstain should shrink by 2–6 tasks. The two iter_013 regressions (3249768e list truncation, 8aef76bc abstention) are the clearest targets; the prompt change may convert a few additional abstentions where evidence is present but partial.
  - Empty predictions should stay at 2–4 (prompt is minimal, generation budget remains 1024).
  - Wrong answers should stay flat or rise by at most 1 (lower abstention threshold increases hallucination risk slightly, but wrong-answer count has been low).
- Trace movement:
  - Top hits for list queries should show expanded sentence counts (e.g., 7 instead of 5 for a 5-item list).
  - Model outputs should contain fewer "Unknown" responses when the gold string appears in retrieved docs.
  - 3249768e and 8aef76bc should move from regressed back to stable pass.
- Side effects to watch:
  - Prompt tokens may rise ~3–8% for list-heavy queries due to the expanded top-hit budget.
  - Risk of 1–2 regressions if the expanded list context crowds out other hits within the global context budget.

## Falsification
- If train passrate does not improve or regresses, the list-expansion budget is still insufficient to preserve the critical item (e.g., cosine-based sentence selection drops the low-similarity list item despite the larger window), or the prompt wording change is too subtle to shift Qwen3 abstention behavior.
- If empty predictions rise above 4, the prompt change unexpectedly triggers hidden reasoning/thinking tokens in Qwen3.
- If the unknown cluster shrinks by fewer than 2 tasks, the dominant failure family in this regime is genuine retrieval misses rather than synthesis conservatism, and the prompt/compression fix is too narrow to matter.

