# Fixed candidate for iteration 24

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
dynamic_contiguous_compression_top8

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, 1024→1536 token generation budget, simplified formatting) and replace the fixed tiered compression (top-2 hits → 5 sentences, next-3 → 3, rest → 2) with two interacting runtime changes:
1. Dynamic relevance-proportional sentence allocation: each hit gets `max_sentences = max(2, min(7, int(2 + 5 * (hit.score / max_score) + 0.5)))`, giving high-scoring hits up to 7 sentences and low-scoring hits 2 sentences.
2. Contiguous-window compression: instead of globally sorting sentences by combined relevance+answer-type score and taking the top-k, find the single highest-scoring sentence in each hit and preserve a contiguous window around it. This keeps local context, list order, and sentence flow intact.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_024/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_024/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_024/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 29592 characters

