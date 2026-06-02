# Fixed candidate for iteration 10

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
answer_type_boosted_retrieval_with_proportional_context

## Mechanism
The dominant failure families are: (1) empty predictions caused by Qwen3 hidden thinking triggered by complex prompts, and (2) retrieval misses / synthesis failures where gold evidence is either not ranked highly enough or gets truncated by fixed per-hit compression.

The new mechanism layers two retrieval-side and context-packing changes on top of proven dual-pass retrieval and simplified formatting:

1. **Answer-type-aware retrieval boosting**: After dual-pass retrieval, detect the expected answer type from the question (numbers, dates, percentages, lists) using lightweight regex heuristics. Boost the scores of retrieved hits that contain matching patterns by 15%. This is general — any retrieval-based QA system benefits from ranking answer-bearing documents higher.

2. **Score-proportional context allocation**: Instead of compressing every hit to a fixed window or showing them at full length, allocate the global `max_context_chars` budget proportionally to each hit's relevance score. Each hit receives a minimum floor (200 chars), and the remainder is distributed by score share. Within each budget, a contiguous window around the most query-relevant sentence is preserved. This ensures high-confidence evidence is preserved in full while low-scoring hits are abbreviated, maximizing the chance the model sees the critical evidence.

The prompt is kept concise and direct (iter_006 style, without cross-hit excerpts) to avoid triggering hidden thinking. The 512-token generation budget is retained.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_010/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_010/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_010/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 21420 characters

