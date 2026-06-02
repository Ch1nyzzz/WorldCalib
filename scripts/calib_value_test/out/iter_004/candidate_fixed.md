# Fixed candidate for iteration 4

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
query_focused_semantic_compression

## Mechanism
Query-focused semantic sentence compression layered on calibrated retrieval ranking and a 512-token generation budget.

1. **Retrieval score calibration** (supporting infrastructure): Remove arbitrary score boosts (+0.1 core, +0.2 summary), normalize RRF scores to [0,1], sort hits purely by relevance score, and compact archival/recall formatting. This restores the retrieval quality that iter_002 proved was load-bearing and that iter_003 catastrophically lost.

2. **Query-aware per-hit sentence compression** (novel mechanism): After retrieval, each hit is compressed by keeping only the 4 sentences most semantically relevant to the query (cosine similarity over tokens), preserving the first line as metadata and restoring original sentence order. This maximizes evidence density: more distinct hits fit in the 6000-char context budget, and the model sees less noise per hit.

3. **Generation budget liberation**: Fix the hidden base.py max_tokens=256 hardcode to 512, add reasoning_content fallback for Qwen3, and keep a concise direct-answer prompt.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_004/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_004/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_004/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 11917 characters

