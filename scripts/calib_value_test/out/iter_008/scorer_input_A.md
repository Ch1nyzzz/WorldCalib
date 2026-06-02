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
The dominant failure family in iter_006 is retrieval misses: ~25-30 of the 50 failures have no gold-bearing documents in the top retrieved set. The current BM25+cosine search uses the full question text, which includes diluting stopwords ("I've", "been", "thinking", "about", "did", "the", etc.). These filler words dilute the lexical signal and cause the search to miss documents that share content words but not the full phrasing.

The new candidate adds a keyword-augmented dual-pass retrieval layer: for each tier (archival and recall), we run the hybrid ranker twice — once with the full query tokens and once with stopwords removed — then fuse the two rankings with RRF. This increases the chance of surfacing documents that match the core content words even when they don't match the full query phrasing. We also add focal sentence highlighting (wrapping the peak-relevance sentence in `** **` markers inside each compressed hit) to help the model attend to the most answer-bearing region, and we soften the system prompt to explicitly permit synthesis across passages and to only abstain when truly no relevant information is present.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.12] (to ~0.55–0.62)
- Failure type movement: The "unknown with irrelevant retrieved docs" cluster should shrink as keyword-augmented retrieval surfaces more relevant passages. The "unknown despite relevant docs" synthesis cluster should also shrink due to focal highlighting and more permissive prompt instructions. Wrong-answer count should stay flat or slightly increase (risk of the more permissive prompt).
- Trace movement: Retrieved documents for previously failed tasks should show higher topical relevance. Spans should show dual-query fusion in metadata.
- Side effects to watch: Token consumption may rise slightly if broader retrieval brings in more total hits before compression; completion tokens should stay stable. Risk of regressions on tasks where stopword removal changes query semantics (e.g., negation-heavy questions).

## Falsification
- If passrate does not improve or regresses, the dual-query mechanism may be retrieving more noise than signal, or the stopword filter may be too aggressive.
- If the "unknown" cluster stays flat while retrieved doc relevance improves, the prompt-induced abstention is the real bottleneck and retrieval changes were secondary.
- If wrong-answer count increases significantly, the softer synthesis prompt is causing hallucination.

