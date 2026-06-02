# iter_015 prediction

## Candidate
multisignal_retrieval_without_answer_boosting

## Mechanism
The candidate replaces answer-signal hit reordering with multi-signal hybrid retrieval (bigram phrase overlap + character 3-gram similarity fused via RRF alongside existing BM25 and token cosine). The base snapshot retains multi-granularity adaptive retrieval (iter_013: archival turns, adaptive sqrt-based limits, four-way fusion) and sentence-window compression (iter_012), but does not include iter_014's list-atomic expansion or directive prompt tweak.

Two failure families drive the change:
1. **Retrieval misses from lexical mismatch**: tasks like gpt4_21adecb5 ("undergraduate degree" vs "bachelor's") and 10d9b85a ("workshops, lectures, and conferences in April") retrieve irrelevant docs because BM25+cosine only matches exact unigrams. Bigram overlap catches multi-word concepts; char n-grams catch morphological variants.
2. **Hit-reordering regressions**: 3249768e and 8aef76bc regressed under answer-signal boosting because shorter hits with partial formatting were promoted above hits with complete content.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.67–0.69)
- Failure type movement:
  - Unknown/abstain cluster should shrink by 2–4 tasks: better retrieval surfaces relevant docs for lexical-mismatch questions, and removing answer-signal boosting restores correct docs to the top for the two known regressions.
  - Wrong-answer cluster should stay roughly stable; multi-signal ranking may trade a few wrong-answer tasks for newly correct ones, but no net drift expected.
  - Empty predictions should remain at 0–2 (reasoning_content fallback is still present).
- Trace movement:
  - For previously failed vocabulary-mismatch tasks, top retrieved docs should shift from tongue twisters or off-topic contracts to semantically relevant passages via bigram/char-ngram overlap.
  - For 3249768e and 8aef76bc, the full relevant doc should appear at rank 1 or 2 instead of a boosted partial hit.
- Side effects to watch:
  - Removing answer-signal boosting could cause 1–2 currently-passing tasks to regress if they relied on reordering to surface an answer-bearing doc into the top-2 uncompressed tier.
  - Prompt token count should stay flat or rise <5% because retrieval limits are unchanged.

## Falsification
- If passrate does not improve or regresses, then multi-signal ranking either (a) fails to surface the relevant docs for lexical-mismatch tasks, or (b) the loss of answer-signal reordering hurts more tasks than it fixes.
- If the unknown cluster does not shrink by at least 2 tasks, the retrieval improvements are not strong enough to compensate for the conservative prompt (iter_014's directive prompt is absent).
- If 3249768e or 8aef76bc do not flip back to pass, the failures are driven by compression truncation or synthesis conservatism rather than hit reordering alone.
