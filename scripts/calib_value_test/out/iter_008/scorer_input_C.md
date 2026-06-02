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
# GROUND TRUTH for iteration 8

Previous iteration (7) observed:
- passrate: None
- failure clusters: null
- avg prompt/completion tokens: None / None

THIS iteration (8) actually observed:
- passrate: 0.53  (over 100 tasks)
- failure clusters: {"correct": 53, "empty": 11, "unknown": 26, "wrong": 10}
- avg prompt/completion tokens: 1588.1 / 205.4
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8, "average_score": 0.8}, "multi-session": {"count": 27, "passrate": 0.4074074074074074, "average_score": 0.4074074074074074}, "single-session-assistant": {"count": 11, "passrate": 0.7272727272727273, "average_score": 0.7272727272727273}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8235294117647058, "average_score": 0.8235294117647058}, "temporal-reasoning": {"count": 26, "passrate": 0.3076923076923077, "average_score": 0.3076923076923077}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter008_keyword_augmented_dual_pass_retrieval_top8.json
- previous candidate_results: None

---
# PREDICTION TO SCORE

# iter_008 prediction

## Candidate
keyword_augmented_dual_pass_retrieval

## Mechanism
The candidate adds stopword-stripped dual-pass hybrid retrieval (BM25+cosine) fused with RRF for both archival and recall tiers, highlights the peak-relevance sentence in each compressed hit with `** **`, and softens the system prompt to explicitly permit synthesis and only abstain when no relevant information exists.

## Outcome prediction
- Train passrate Δ: [+0.08, +0.18] (from 0.50 baseline to ~0.58–0.68)
- Failure type movement:
  - Retrieval-miss abstentions should shrink: fewer "unknown" answers where the gold document was missed because stopwords diluted the query embedding.
  - False-abstention cluster should shrink: tasks where relevant docs were retrieved in iter_006 but the model still emitted "unknown" (e.g., DIY sealant, cocktail fifth bottle) should flip to passed.
  - Misreading/synthesis-error cluster may grow slightly because the softer prompt can cause hallucinations on low-relevance retrievals.
- Trace movement:
  - Retrieved hit metadata should show `search_mode` values reflecting dual-pass fusion (e.g., "bm25+semantic" from both full and keyword passes).
  - Fewer predictions should end with "unknown"; more should quote exact phrases from highlighted sentences.
  - Some previously empty predictions should now contain concise answers.
- Side effects to watch:
  - Token consumption should stay flat or rise modestly (+5–10%) because highlighting adds a few characters per hit but hit count limits are unchanged.
  - Runtime is negligible change (two extra BM25+cosine passes per tier).
  - Risk of 2–4 regressions where the softer prompt hallucinates an answer when retrieval is truly irrelevant.

## Falsification
- If train passrate increases by less than +0.05, the dual-pass retrieval is not rescuing the hypothesized ~25–30 retrieval-miss failures, or the RRF fusion is ineffective.
- If the abstention rate (fraction of predictions containing "unknown") does not drop by at least 10 percentage points, the prompt and highlighting changes are not changing model behavior.
- If regressions exceed 4 passed→failed tasks, the softer prompt is causing harmful hallucinations that outweigh retrieval gains.

