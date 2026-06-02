# Fixed candidate for iteration 11

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
fixed_window_list_skeleton_highlighting

## Mechanism
The dominant failure family is list-truncation-induced abstention: when proportional or fixed-window compression cuts off a numbered/bullet list after the first few items, the model sees an incomplete list and answers "unknown." This was observed in `3249768e` (gin cocktail bottles — passed only in iter_006 with fixed 5-sentence window, failed in all proportional/allocation iterations) and `8cf51dda` (endometrial cancer objectives — passed in iter_006/008 with fixed window or highlighting, failed in iter_009/010).

The new mechanism is a structure-aware compression function that:
1. Detects list blocks (numbered, bulleted, or labeled items) inside a retrieved hit.
2. When compressing a list-bearing hit, truncates each item to its heading/first sentence rather than dropping whole items or cutting mid-description. This preserves the complete list skeleton within the per-hit budget.
3. For non-list content, falls back to a fixed 5-sentence contiguous window around the most query-relevant sentence (proven in iter_006).
4. Wraps the peak sentence in `**` to guide the model's attention (observed to help in iter_008).

The prompt stays concise and direct (iter_006 style) to avoid Qwen3 hidden-thinking empty outputs. The 512-token generation budget is retained.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_011/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_011/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_011/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 20227 characters

