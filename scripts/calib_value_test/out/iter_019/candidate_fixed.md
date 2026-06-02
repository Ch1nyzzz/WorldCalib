# Fixed candidate for iteration 19

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
list_block_extraction_from_long_docs

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, adaptive limits, sentence compression, 1024-token budget, minimal prompt) that achieved 0.69 passrate. Replaces the brittle ratio-based list-preservation heuristic (`_is_short_list`) with a targeted list-block extraction mechanism that operates inside `_compress_hit`. When a document is too long for the existing short-list preservation (><8 units), the new code detects contiguous list blocks (2–6 items), scores them by query relevance, and extracts the best block plus ±1 context unit. The extracted text is bounded to `max_sentences + 1` units, so it never consumes more context budget than normal compression and often consumes less. This fixes the 8cf51dda regression (3 objectives embedded in a 14-unit grant document) without the context-budget regressions that iter_018’s `len(units) <= 12` threshold caused.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_019/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_019/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_019/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 29134 characters

