# Fixed candidate for iteration 28

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
answer_type_boost_aggregation

## Mechanism
Add answer-type-aware boosting to the retrieval ranking and adaptive MMR/synthesis for aggregation queries.

1. **Retrieval boosting**: After multi-signal fusion, docs that contain the expected answer type (numbers for "how much/many", dates for "when/how long", yes/no for boolean queries, list markers for enumeration queries) receive a small score boost. This helps surface evidence that is semantically relevant but lexically mismatched.

2. **Adaptive MMR for aggregation**: When aggregation signals are detected ("total", "all", "how many", "sum", "combined", "every", "each", "list"), the MMR candidate pool expands from k*3 to k*4 and lambda drops from 0.9 to 0.8, trading a small amount of relevance for more diversity. This brings scattered evidence into the context window.

3. **Aggregation synthesis hint**: For aggregation queries, the system prompt includes a one-line note: "When the question asks for a total, count, or list, carefully review all retrieved entries and combine the relevant facts before answering." This directly addresses synthesis failures where evidence is present but the model only uses a subset.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_028/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_028/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_028/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 39772 characters

