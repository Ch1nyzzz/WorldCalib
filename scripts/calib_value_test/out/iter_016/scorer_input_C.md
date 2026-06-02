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
# GROUND TRUTH for iteration 16

Previous iteration (15) observed:
- passrate: 0.66
- failure clusters: {"correct": 66, "empty": 4, "unknown": 22, "wrong": 8}
- avg prompt/completion tokens: 1654.5 / 220.7

THIS iteration (16) actually observed:
- passrate: 0.69  (over 100 tasks)
- failure clusters: {"correct": 69, "empty": 1, "unknown": 21, "wrong": 9}
- avg prompt/completion tokens: 1592.4 / 214.6
- per-type score_breakdown: {"knowledge-update": {"count": 15, "passrate": 0.8666666666666667, "average_score": 0.8666666666666667}, "multi-session": {"count": 27, "passrate": 0.5555555555555556, "average_score": 0.5555555555555556}, "single-session-assistant": {"count": 11, "passrate": 0.9090909090909091, "average_score": 0.9090909090909091}, "single-session-preference": {"count": 4, "passrate": 0.0, "average_score": 0.0}, "single-session-user": {"count": 17, "passrate": 0.8823529411764706, "average_score": 0.8823529411764706}, "temporal-reasoning": {"count": 26, "passrate": 0.6153846153846154, "average_score": 0.6153846153846154}}

Raw artifacts you MAY read to verify trace/retrieval/span claims:
- actual candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter016_sentence_surfacing_with_structure_preservation_top8.json
- previous candidate_results: runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/candidate_results/iter015_multisignal_retrieval_without_answer_boosting_top8.json

---
# PREDICTION TO SCORE

# iter_016 prediction

## Candidate
sentence_surfacing_with_structure_preservation

## Mechanism
The change replaces peak-centered sentence-window compression with per-hit global relevance sorting: each hit is split into sentences/list-units, units are scored by query-token cosine similarity, and the top-N most relevant units are surfaced first within the hit. Complete short structured lists (≤8 items, ≥50% list markers) are preserved intact without truncation or reordering. Numbered list items (e.g., "1. Sweet Vermouth") are now correctly detected as atomic units, fixing a bug in the prior sentence splitter.

This targets the dominant residual failure family where evidence is present in retrieved hits but the model either cannot find it (synthesis failure) or the evidence is in a structured list that gets truncated by coarse compression. Two independent evidence sources support this:
1. Task 3249768e (cocktail fifth bottle): iter_014–015 list-atomic compression still truncated the 5-item list to ~4 items; the model explicitly says "only the first bottle (Sweet Vermouth) is mentioned."
2. Task 8aef76bc (sealant): the top-2 recall hit contains "Seal the vase with Mod Podge or another sealant," yet the model outputs unknown — the sentence is buried in a long hit and missed by peak-window compression.
3. Task 7405e8b1 (HelloFresh vs UberEats): UberEats discount evidence appears in retrieved hits 3–4 but the model says it is missing, indicating salience failure within compressed hits.

The mechanism should transfer because any retrieval-then-synthesis pipeline over long documents risks (a) truncating structured lists and (b) burying answer-bearing sentences inside long passages. Surfacing the most relevant units first is a general information-flow improvement.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.05] (to ~0.68–0.71)
- Failure type movement:
  - List-truncation cluster shrinks by 1–2 tasks (3249768e likely fixed; 8cf51dda may recover if its numbered objectives are now preserved as a short list).
  - Synthesis/abstention cluster shrinks by 1–2 tasks (8aef76bc and 7405e8b1 should see answer-bearing sentences moved to the front of their hits).
  - Empty-prediction cluster (8cf51dda, 982b5123, gpt4_21adecb5) is likely stable: these tasks showed empty predictions with 1024 completion tokens in iter_014–015, suggesting a model-level max_tokens/reasoning loop issue rather than a context-salience issue.
  - Wrong-answer cluster: stable.
- Trace movement:
  - For 3249768e, compressed top hits should now contain all five bottles as a preserved list block instead of a truncated subset.
  - For 8aef76bc, the sealant sentence should appear in the first 1–3 units of the compressed DIY hit.
  - For 7405e8b1, UberEats discount sentences should rank highly within hits 3–4 and appear at the front of those blocks.
- Side effects to watch:
  - Prompt tokens may rise slightly for hits containing short lists (preserved completely instead of truncated).
  - Regression risk on tasks that depend on chronological or causal coherence within a single long hit, because global relevance sorting reorders sentences and breaks narrative flow. Likely low (only long hits are reordered, and short lists are exempt), but non-zero.

## Falsification
- If passrate does not improve or regresses, either (a) sentence reordering breaks coherence in more tasks than it helps, or (b) the recoverable failures are driven by retrieval misses or model-level generation issues that context reorganization cannot fix.
- If 3249768e remains failed, short list preservation is insufficient — the 5-bottle list may be split across multiple hits or missed by the list detector.
- If 8aef76bc remains failed, the synthesis failure is not due to evidence salience but to a deeper model bias or reasoning behavior.
- If the empty-prediction tasks (8cf51dda, 982b5123, gpt4_21adecb5) remain empty with 1024 completion tokens, the failure family is model-level max-token exhaustion, not context packing.

