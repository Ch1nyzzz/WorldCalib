# Fixed candidate for iteration 2

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
memgpt_calibrated_ranking

## Mechanism
Two failure families from iter_001:
1. Cross-tier score miscalibration: summary gets 0.2+cosine (≈0.30), core gets 0.1+cosine (≈0.15), but archival/recall RRF maxes at ~0.03. This forces the top-2 retrieval slots to always be summary/core metadata, pushing answer-bearing archival/recall passages down or out of the 6000-char budget.
2. Empty predictions: 25 fails produced empty strings while consuming exactly 256 completion tokens, suggesting the model burns its budget on hidden reasoning/thinking tokens or verbose quoting before reaching FINAL ANSWER.

Fix: (a) remove fixed additive boosts from summary/core scores and normalize RRF to [0,1] so relevant docs from any tier can compete; (b) increase max_tokens to 512; (c) simplify the prompt to direct concise answering without quoting; (d) keep iter_001's compact formatting.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_002/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_002/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 8596 characters

