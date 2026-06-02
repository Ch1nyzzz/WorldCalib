# Fixed candidate for iteration 3

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
token_economical_direct_extraction

## Mechanism
Three coordinated changes that address the dominant failure families in iter_002:

1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, which silently neutralized iter_002's attempt to raise the limit. This hard cap caused 18 empty predictions (all hitting exactly 256 completion tokens) and capped every other task at ≤256 tokens. Raising it to 512 removes the artificial ceiling.

2. **Direct-answer prompt redesign**: The current prompt lets the model generate reasoning before "FINAL ANSWER:", wasting tokens and increasing truncation risk. Adding "Do not explain your reasoning" suppresses verbose preamble, leaving more budget for the actual answer.

3. **Equitable per-hit context packing**: The current builder includes full hits until the 6000-char budget is exhausted, so a single 1700-char hit can crowd out 2-3 other relevant docs. Dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`) ensures more hits are visible, increasing evidence diversity.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_003/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_003/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py

Patch size: 4265 characters

