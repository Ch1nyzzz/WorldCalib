# Fixed candidate for iteration 13

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
multi_granularity_adaptive_retrieval

## Mechanism
The dominant failure family is retrieval misses: 31 of 43 failures in iter_012 have the gold answer string absent from all retrieved hits. Evidence source 1: task 1a1907b4 (cocktail suggestions) retrieves 12 docs about scented sprays and lens purchases; the mixology-class doc is missing. Evidence source 2: task 129d1232 (total charity raised) retrieves cycling tips and waste reduction; the docs with additional fundraising amounts are missing. Evidence source 3: task 10d9b85a (April workshop days) retrieves joke questions and theatre reviews; the April attendance doc is missing.

The new mechanism is multi-granularity archival indexing paired with adaptive retrieval limits:
1. **Turn-level archival passages** (chunk_size=1) are indexed alongside the original chunk passages. This reduces relevance dilution: a relevant turn is no longer penalized for sharing a chunk with irrelevant neighbors, so it can rank higher in sparse retrieval.
2. **Four-pass retrieval** runs BM25+cosine on both chunk and turn indexes with both the full query and a keyword-only (stopword-removed) query, then fuses the four rankings with RRF. This increases the chance that a relevant doc surfaces.
3. **Adaptive retrieval limits** scale with sqrt(corpus size) instead of fixed top_k fractions, ensuring large conversations retrieve more candidates.
4. **Sliding-scale compression** (5 sentences for top 2, 3 for next 3, 2 for rest) preserves context budget while fitting the larger pool.
5. **Load-bearing fixes kept**: 1024-token generation budget, reasoning_content fallback, minimal prompt, compact formatting, score-first tier sorting.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_013/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_013/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_013/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 26079 characters

