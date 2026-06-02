# Fixed candidate for iteration 16

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
sentence_surfacing_with_structure_preservation

## Mechanism
The dominant remaining failure families are (1) synthesis failures where evidence is present in retrieved hits but the model cannot extract it, and (2) list-truncation regressions where structured enumerations are compressed away. Two independent evidence sources support this:
1. Task 8aef76bc (sealant): the retrieved hit contains "Seal the vase with Mod Podge or another sealant," yet the model answers unknown — a clear synthesis failure.
2. Task 7405e8b1 (HelloFresh vs UberEats): UberEats discount evidence appears in multiple lower-ranked retrieved hits (indices 3, 4, 18, 19, 25, 27), yet the model says the context lacks UberEats discount info — evidence is present but not salient enough.
3. Task 3249768e (cocktail fifth bottle): a 5-item list is compressed to 4 items, cutting off the 5th bottle (Absinthe) — a structure-truncation failure.

The new mechanism restructures how each hit is presented to the model: (a) split each hit into sentences/list-units, (b) score each unit by query relevance, (c) re-order units so the most relevant ones appear first, and (d) preserve complete short lists (≤8 items) without reordering or truncation. This surfaces answer-bearing content front-and-center within each hit without adding any preamble, markdown formatting, or cross-hit complexity. It is general because any QA system benefits from having the most relevant evidence visible first, and short structured lists are ubiquitous in conversational memory.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_016/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_016/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_016/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 27414 characters

