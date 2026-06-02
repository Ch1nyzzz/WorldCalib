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
Restore the iter_020 stack (0.69 passrate) and layer two runtime changes in `model.py` plus a generation-budget increase in `base.py`:
1. Dynamic relevance-proportional sentence allocation replaces fixed tiered compression (5/3/2). Each hit gets `max(2, min(7, round(2 + 5 * hit.score/max_score)))`, giving the strongest hits up to 7 sentences.
2. Contiguous-window compression replaces globally sorted top-k sentence selection. The highest-scoring sentence in a hit is located, and a contiguous window around it is preserved, keeping list order and local context intact.
3. Generation budget raised from 1024 to 1536 tokens.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from 0.69 to ~0.70–0.73)
- Failure type movement:
  - Empty-output cluster shrinks from 4 to 0–2. Diagnostic evidence: all 4 iter_020 empty tasks emitted exactly 1024 completion tokens, confirming max_tokens truncation. Historical traces show 2 of these tasks (gpt4_21adecb5, 4f54b7c9) passed under prior iterations when not truncated; gpt4_7abb270c consistently fails; 0bc8ad93 consistently outputs a wrong answer ("yes/with a friend") when given budget. Thus ~2 of the 4 empties should convert to passes.
  - Unknown/abstain cluster shrinks by 1–3 tasks. The contiguous window preserves list order and local context in top hits, and the dynamic allocation gives the top 1–2 hits up to 7 sentences (vs 5), which should surface enough context for a few synthesis failures where evidence was present but scattered or truncated.
  - Wrong-answer cluster stays roughly flat (7±1). 0bc8ad93 may convert from empty to wrong, offsetting any wrong→pass improvements elsewhere.
- Trace movement:
  - Fewer predictions with exactly 1024 completion tokens.
  - More top-hit blocks showing contiguous sentence sequences (especially numbered/bulleted lists) rather than globally reordered sentences.
- Side effects to watch:
  - Average prompt token count may rise slightly because top hits can now expand to 7 sentences.
  - Risk of 0–2 regressions on tasks where the answer depends on two widely separated passages within a single long document; the contiguous window cannot cherry-pick both regions, whereas iter_020's global sort could.

## Falsification
- If train passrate does not improve by at least +0.01, then either (a) the 1536-token ceiling does not resolve the empty-output truncation, (b) contiguous-window compression is missing scattered evidence in top hits and causing regressions that cancel the empty-output gains, or (c) the dynamic allocation is adding noisy low-scoring sentences to high-scoring hits.
- If the wrong-answer count rises by more than 2, contiguous window is destroying cross-region evidence in long documents.
- If empty outputs do not shrink despite 1536 tokens, Qwen3 hidden-thinking behavior is not governed by the explicit generation budget.

