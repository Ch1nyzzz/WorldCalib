# Fixed candidate for iteration 20

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
multi_objective_compression_with_answer_type_scoring

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, multi-granularity archival, adaptive limits, 1024-token budget, minimal prompt). Replaces the single-objective sentence compression in `_compress_hit` with a multi-objective score that combines (0.65) query-relevance cosine similarity with (0.35) answer-type likelihood heuristics. The answer-type scorer boosts sentences that contain numbers for quantitative questions, dates/time words for temporal questions, yes/no markers for binary questions, and list markers for enumeration questions. This surfaces answer-bearing content that pure relevance scoring buries. Additionally, compressed units are joined with newlines instead of spaces to preserve list structure and sentence boundaries.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_020/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_020/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_020/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 29267 characters

