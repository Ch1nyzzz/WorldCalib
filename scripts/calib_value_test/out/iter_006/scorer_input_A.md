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
# GROUND TRUTH for iteration 6

Previous iteration (5) observed:
- passrate: 0.39
- failure clusters: {"correct": 39, "empty": 3, "unknown": 48, "wrong": 10}
- avg prompt/completion tokens: 1318.9 / 149.8

THIS iteration (6) actually observed:
- passrate: 0.5  (over 100 tasks)
- failure clusters: {"correct": 50, "empty": 3, "unknown": 38, "wrong": 9}
- avg prompt/completion tokens: 1448.5 / 170.9
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.25, "average_score": 0.25}, "single-session-user": {"count": 17, "passrate": 0.7647058823529411, "average_score": 0.7647058823529411}, "temporal-reasoning": {"count": 26, "passrate": 0.19230769230769232, "average_score": 0.19230769230769232}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter006_contiguous_window_compression_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter005_structure_preserving_adaptive_context_top8.json

---
# PREDICTION TO SCORE

# iter_006 prediction

## Candidate
contiguous_window_compression

## Mechanism
Replace iter_005’s destructive list-block preservation with bounded contiguous relevance windows.

1. **Calibrated retrieval scaffold** (re-applied from iter_004): Remove arbitrary score boosts on summary/core memory, normalize RRF scores to [0,1], sort hits by score-first then tier, compact archival/recall/core formatting, and truncate archival turns to 300 chars. This is load-bearing and must be in place before any model-layer change.

2. **Contiguous relevance-window compression** (new): For each retrieved hit, split content into sentences, score each by query cosine similarity, find the peak-scoring sentence, and keep a contiguous 4-sentence window centered on that peak (±1–2 sentences). Always preserve the metadata line. Maximum 5 sentences per hit. This bounds per-hit length tightly, avoids the context-bloat that caused iter_005’s regression, and preserves local coherence better than iter_004’s scattered top-4 selection.

3. **Synthesis-permissive prompt**: Replace the overly restrictive “use exact words / do not explain reasoning” formulation with explicit permission to combine facts across passages and perform simple arithmetic/comparison when the supporting facts are present. This targets the over-abstention cluster where evidence is present but the model refuses to synthesize.

4. **512-token generation ceiling** in base.py and model.py default, with reasoning_content fallback for Qwen3 empty-content responses.

## Outcome prediction
- Train passrate Δ: [+0.06, +0.12] (from iter_004’s 0.49 baseline to ~0.55–0.61)
- Failure type movement:
  - “unknown/empty” cluster shrinks by 6–10 (synthesis permission + coherent context windows reduce abstention)
  - “wrong_answer” cluster stable or shrinks slightly (contiguity preserves negation and modifier context)
  - No regressions from iter_004 (bounded windows prevent context bloat)
- Trace movement:
  - More predictions contain synthesized values (sums, differences, comparisons)
  - Completion tokens stable (~100–250)
  - Prompt tokens stable or slightly lower than iter_005 (no list-block bloat)
- Side effects to watch:
  - Risk of hallucination from synthesis permission (mitigated by “using only the retrieved memory” grounding)
  - Risk that peak-centered windows miss answers at the very start or end of a long hit (mitigated by always including metadata line)

## Falsification
- Passrate below 0.50 would mean contiguous-window compression is not better than iter_004’s scattered top-4, or the synthesis prompt causes hallucinations that outweigh gains.
- “unknown” cluster not shrinking would mean over-abstention is driven by retrieval misses, not synthesis reluctance.
- Regressions above 3 would indicate the windowing still drops critical evidence.
