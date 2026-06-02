# Fixed candidate for iteration 14

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
list_atomic_compression_with_directive_prompt

## Mechanism
The dominant failure family from iter_013 is synthesis failures where evidence is present in retrieved hits but the model either abstains or extracts a truncated answer. Two independent evidence sources support this:
1. Task 3249768e (cocktail fifth bottle): the correct doc with Absinthe is retrieved and re-sorted to the top by answer-signal boosting, but sliding-scale sentence-window compression (5 sentences max) truncates the 5-item list to 4 items, cutting off Absinthe. The model explicitly says "only the first bottle (Sweet Vermouth) is mentioned."
2. Task 8aef76bc (sealant): "Mod Podge or another sealant" appears in a top-ranked recall doc, yet the model outputs "Unknown," indicating synthesis conservatism.

The new mechanism has two parts:
1. **List-atomic compression**: In `build_answer_messages`, when a top hit (idx ≤ 2) contains a structured list with 3+ items and the question asks for a list-related answer (detected by existing `_answer_type_patterns`), the compression budget is expanded to `list_items + 2` sentences instead of the fixed 5. This preserves the complete list block while still bounding per-hit length.
2. **Directive prompt tweak**: The system prompt is changed from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

Both changes are bounded: list expansion applies only to top-2 hits with clear list structure, and the prompt change is a wording shift, not a reasoning chain addition, so it should not trigger Qwen3 hidden thinking.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_014/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_014/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_014/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 26583 characters

