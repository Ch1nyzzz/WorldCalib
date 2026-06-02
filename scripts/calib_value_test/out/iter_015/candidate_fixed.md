# Fixed candidate for iteration 15

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

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

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_015/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_015/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_015/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 27034 characters

