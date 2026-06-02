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
# GROUND TRUTH for iteration 24

Previous iteration (23) observed:
- passrate: None
- failure clusters: null
- avg prompt/completion tokens: None / None

THIS iteration (24) actually observed:
- passrate: 0.62  (over 100 tasks)
- failure clusters: {"correct": 62, "empty": 0, "unknown": 26, "wrong": 12}
- avg prompt/completion tokens: 1503.5 / 199.8
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.6, "average_score": 0.6}, "multi-session": {"count": 27, "passrate": 0.48148148148148145, "average_score": 0.48148148148148145}, "single-session-assistant": {"count": 11, "passrate": 0.9090909090909091, "average_score": 0.9090909090909091}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.9411764705882353, "average_score": 0.9411764705882353}, "temporal-reasoning": {"count": 26, "passrate": 0.5384615384615384, "average_score": 0.5384615384615384}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter024_dynamic_contiguous_compression_top8_top8.json
- previous candidate_results: None

---
# PREDICTION TO SCORE

# iter_024 prediction

## Candidate
dynamic_contiguous_compression_top8

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, 1024→1536 token generation budget, simplified formatting) and replace the fixed tiered compression (top-2 hits → 5 sentences, next-3 → 3, rest → 2) with two interacting runtime changes:
1. Dynamic relevance-proportional sentence allocation: each hit gets `max_sentences = max(2, min(7, int(2 + 5 * (hit.score / max_score) + 0.5)))`, giving high-scoring hits up to 7 sentences and low-scoring hits 2 sentences.
2. Contiguous-window compression: instead of globally sorting sentences by combined relevance+answer-type score and taking the top-k, find the single highest-scoring sentence in each hit and preserve a contiguous window around it. This keeps local context, list order, and sentence flow intact.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.06] (from 0.69 to ~0.71–0.75)
- Failure type movement: Wrong-answer cluster should shrink by 2–4 tasks (contiguous windows preserve complete numerical/list context that global top-k reordering drops). Empty-output cluster should shrink by 1–2 tasks due to the 1536-token ceiling. Unknown/abstain cluster may shrink by 1–2 tasks if better context preservation surfaces missed evidence.
- Trace movement: Fewer truncated lists and miscounted totals. More hits should retain complete local context around the answer-bearing region.
- Side effects to watch: Average prompt token consumption may rise by ~30–50 tokens per task because mid-ranked hits now get 3–5 sentences instead of a flat 2–3. No expected regressions because the mechanism only changes which sentences are kept, not prompt wording or retrieval logic.

## Falsification
If wrong-answer count does not shrink, contiguous-window preservation is not helping aggregation and the failure is either retrieval miss or model reasoning error. If empty outputs persist at 1536 tokens, Qwen3 hidden thinking is not governed by generation budget. If passrate drops below 0.69, the interaction between longer average contexts and Qwen3 synthesis is negative.

