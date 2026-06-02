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
The dominant failure families remaining after iter_015 are (1) synthesis failures where evidence is present in retrieved hits but the model cannot extract it, and (2) list-truncation regressions where structured enumerations are compressed away. Three independent evidence sources support this:
1. Task 8aef76bc (sealant): the retrieved hit contains "Seal the vase with Mod Podge or another sealant," yet the model answers unknown — a clear synthesis failure where the answer-bearing sentence is buried in a long list hit.
2. Task 7405e8b1 (HelloFresh vs UberEats): UberEats discount evidence appears in multiple lower-ranked retrieved hits (indices 3, 4, 18, 19, 25, 27), yet the model says the context lacks UberEats discount info — evidence is present but not salient enough within each hit.
3. Task 3249768e (cocktail fifth bottle): a 5-item list is compressed to 4 items, cutting off the 5th bottle (Absinthe) — a structure-truncation failure caused by aggressive sentence-level compression.

The mechanism restructures how each hit is presented to the model: (a) split each hit into sentences/list-units, (b) score each unit by query relevance, (c) re-order units so the most relevant ones appear first, and (d) preserve complete short lists (≤8 items) without reordering or truncation. This surfaces answer-bearing content front-and-center within each hit without adding any preamble, markdown formatting, or cross-hit complexity. It is general because any QA system benefits from having the most relevant evidence visible first, and short structured lists are ubiquitous in conversational memory.

A counterexample class the patch was designed not to hurt: tasks where the answer requires narrative flow or temporal sequencing across sentences within a hit. The mechanism only reorders non-list prose units; short lists are preserved in original order, so sequence-dependent answers inside preserved lists are not disrupted.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.06] (to ~0.69–0.72)
- Failure type movement: The unknown/abstain cluster should shrink by 3–5 tasks (improved synthesis for buried evidence like 8aef76bc and 7405e8b1, plus list preservation for 3249768e). The list-truncation regression cluster should shrink by 2–3 tasks. Empty predictions should stay flat at 3–4 tasks because the mechanism does not address Qwen3 hidden-thinking empty outputs (e.g., 8cf51dda). Wrong answers might increase by 0–1 if sentence reordering occasionally destroys cross-sentence context needed for disambiguation.
- Trace movement: For previously failed synthesis tasks (8aef76bc, 7405e8b1), traces should show the answer-bearing sentence appearing in the first 1–2 lines of the relevant hit rather than buried mid-document. For 3249768e, the trace should show a complete 5-item list instead of a truncated 4-item list. For stable-pass tasks, traces should show hit content that is no more than 10–15% longer on average due to short-list preservation.
- Side effects to watch: Slightly higher prompt token counts if multiple short lists are preserved in full. Risk of regression on narrative-flow tasks where temporal or causal ordering within a hit matters (e.g., "what happened after X?"). Risk that lower-ranked hits with surfaced sentences still get truncated at the hit level before the surfaced content reaches the model.

## Falsification
- If train passrate does not improve or regresses, sentence reordering is destroying necessary context flow within hits, or list preservation is crowding out other hits and reducing overall evidence diversity.
- If 8aef76bc or 3249768e remain failed, the synthesis/truncation issue is deeper than content ordering (e.g., the model still cannot recognize the answer even when it is the first sentence of the hit).
- If the empty-output cluster grows from 4 tasks, the sentence-reordering logic is interacting badly with Qwen3's hidden thinking behavior, possibly by increasing per-hit length variability.
- If wrong-answer count increases by more than 2 tasks, the relevance-scoring signal is surfacing distractor sentences that confuse the model.

