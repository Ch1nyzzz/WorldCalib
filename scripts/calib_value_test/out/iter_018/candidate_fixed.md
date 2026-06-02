# Fixed candidate for iteration 18

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
contiguous_list_block_preservation

## Mechanism
Iter_017 catastrophically regressed from 0.69 to 0.17 because it applied the abstention-retry mechanism on top of the clean source snapshot without re-applying iter_016's load-bearing retrieval improvements (multi-granularity indexing, multi-signal fusion, adaptive limits, sentence compression, 1024-token budget). This candidate first restores the full iter_016 proven stack, then replaces the brittle ratio-based list-preservation heuristic (`list_markers >= len(units) * 0.5`) with contiguous list-block detection. The ratio-based approach fails when background prose dilutes the list ratio below 50%, causing structured answers (numbered objectives, bottle lists, DIY steps) to be compressed and reordered, destroying the structure the model needs. Contiguous-block detection looks for runs of 2+ consecutive list-marker lines and preserves the complete hit whenever such a block exists and the total unit count is reasonable (≤12). This is more robust because it depends on local structural contiguity, not global statistics, so embedding prose cannot hide a list block.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_018/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_018/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_018/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 27454 characters

