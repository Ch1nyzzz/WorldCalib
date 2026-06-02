# Fixed candidate for iteration 12

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
answer_signal_prioritized_two_tier_context

## Mechanism
The dominant failure family is Qwen3 hidden-thinking truncation causing empty predictions (~10 tasks in iter_011) and prompt-complexity-induced abstention. The iter_011 list-skeleton + ** highlighting mechanism made both worse by increasing prompt complexity and trigger tokens.

The new mechanism is a two-tier context packing strategy paired with a larger generation budget:
1. **Increase max_tokens to 1024** to give Qwen3 room to finish hidden thinking and still emit an answer.
2. **Answer-signal prioritization**: detect answer-type cues (number, date, list, yes/no) from the question; reorder retrieved hits so that hits containing matching cues appear first.
3. **Two-tier compression**: Tier-1 hits (top 2, or all answer-signal hits if fewer) get minimal compression (up to 1000 chars) so the model can read the most promising evidence in full. Tier-2 hits get aggressive 3-sentence window compression to preserve context budget.
4. **Minimal prompt**: strip all formatting triggers (** highlighting, list-preservation logic, verbose instructions) and use the simplest direct-answer instruction.

The retrieval foundation is kept load-bearing: dual-pass keyword retrieval, RRF score normalization, score-first tier sorting, compact core/hit formatting, 300-char archival truncation, and reasoning_content fallback.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_012/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_012/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_012/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 20056 characters

