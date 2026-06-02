# Fixed candidate for iteration 9

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
cross_hit_evidence_distillation

## Mechanism
The dominant failure families in iter_008 are (1) empty/truncated outputs caused by Qwen3 consuming the 512-token budget in hidden thinking, and (2) synthesis failures where the answer is present in retrieved docs but buried or scattered across long passages.

The new candidate layers two changes on top of the proven dual-pass retrieval, score calibration, and formatting from iter_008:

1. **Simplified direct-answer prompt**: Replace the verbose iter_008 prompt with a concise instruction that explicitly forbids step-by-step reasoning and demands an immediate answer. This reduces hidden thinking that consumes completion tokens.

2. **Cross-hit evidence distillation**: Before assembling the context, score every sentence in every retrieved hit by cosine similarity to the query. Extract the top-N highest-scoring sentences across all hits and present them as "Relevant excerpts" at the very top of the prompt, with inline provenance (which hit each sentence came from). The full compressed hits follow below. This front-loads the most answer-bearing evidence, reducing the cognitive load on the model and making it less likely to miss scattered facts or run out of tokens while reasoning.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_009/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_009/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_009/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 19670 characters

