# iter_015 prediction

## Candidate
multisignal_retrieval_without_answer_boosting

## Mechanism
The dominant failure family from iter_013 and iter_014 is retrieval misses caused by vocabulary mismatch between queries and documents (e.g., "undergraduate degree" vs "bachelor's", "cocktail bar" vs "gin-based cocktails"). The current hybrid ranker (BM25 + unigram cosine) only captures exact token overlap and fails on paraphrased or morphologically related terms. Two independent evidence sources support this:
1. Task gpt4_21adecb5 (undergrad→master's): the query asks about "undergraduate degree" and "master's thesis" but the relevant conversation says "bachelor's" and "thesis submission." BM25+cosine returns completely irrelevant contract-law docs because they share the token "completion."
2. Task 10d9b85a (April workshops): the query asks about "workshops, lectures, and conferences in April" but the top retrieved docs are tongue twisters and seasonal mood discussions, showing the lexical matcher is failing to find the relevant session.

In addition, iter_013's answer-signal boosting (reordering hits by detected answer-type patterns) caused regressions on list questions: 3249768e (cocktail fifth bottle) and 8aef76bc (sealant) both regressed from pass to fail under this reordering, likely because shorter hits with partial list formatting were boosted above hits with complete content.

The new mechanism has two parts:
1. **Multi-signal hybrid ranking**: Add bigram phrase overlap and character n-gram similarity to `_hybrid_rank` in memgpt_scaffold.py. Bigram overlap catches multi-word concepts (e.g., "master's thesis" as a phrase). Character n-gram similarity catches morphological variants (e.g., "undergraduate" and "bachelor's" share no unigrams but some character 3-grams). Both signals are fused via RRF alongside existing BM25 and token cosine, with lower weights so they supplement rather than dominate.
2. **Remove answer-signal boosting**: In model.py, revert `build_answer_messages` to use the original retrieval ordering instead of reordering hits by `_has_answer_signal`. This eliminates the hit-reordering regressions observed in iter_013 and iter_014.

Both changes are general: multi-signal ranking improves any retrieval task with lexical variation, and removing answer-signal boosting simplifies the synthesis pipeline without task-specific logic.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.08] (to ~0.69–0.74)
- Failure type movement: Unknown/abstain cluster should shrink by 3–5 tasks (improved retrieval for paraphrased queries). Wrong answers might shrink by 1–2 tasks (better evidence ranking reduces partial-retrieval errors). Empty predictions should stay at 0–3.
- Trace movement: For previously failed vocabulary-mismatch tasks, the relevant doc should appear in the top-3 retrieved hits instead of being buried or absent. For 3249768e and 8aef76bc, the top hit should contain the complete list or sealant info without harmful reordering.
- Side effects to watch: Slightly higher retrieval computation (char n-grams over all docs). Slightly longer prompts if more relevant hits are retrieved. Risk of regression on tasks where exact unigram matching was already optimal is low because new signals are weighted lower.

## Falsification
- If passrate does not improve or regresses, either multi-signal ranking introduces noise that drowns out exact matches, or removing answer-signal boosting drops previously-correct tasks that relied on answer-pattern hits being front-loaded.
- If the unknown cluster does not shrink by at least 2 tasks, the retrieval misses are driven by something other than vocabulary mismatch (e.g., the relevant docs are truly absent from the corpus, not just poorly ranked).
- If 3249768e or 8aef76bc remain failed, the list-truncation issue is not caused by hit reordering but by a deeper prompt/context problem.
