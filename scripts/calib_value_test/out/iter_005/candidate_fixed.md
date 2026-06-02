# Fixed candidate for iteration 5

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
structure_preserving_adaptive_context

## Mechanism
Replace fixed 4-sentence per-hit compression with structure-aware adaptive context assembly.

1. **List-atomic compression**: Detect numbered/bullet lists within retrieved hits. When any list item is query-relevant, preserve the entire list block rather than compressing it to a fixed sentence count. This fixes regressions like 8cf51dda (grant objectives compressed away) and persistent failures like 3249768e (cocktail list truncated).

2. **Dynamic relevance-weighted sentence budgets**: Allocate sentences per hit proportionally to its relevance score instead of a flat 4-sentence cap. High-confidence hits (score > 0.95) get up to 8 sentences; medium-confidence hits get up to 5; low-confidence hits get up to 3. This preserves more signal from the hits most likely to contain the answer while still trimming noise from tail hits.

3. **Archival list preservation**: In memgpt_scaffold.py, make the 300-char turn truncation list-aware. If a turn contains a numbered or bulleted list, preserve the full list even if it exceeds the character limit. This recovers answers that live inside truncated list turns.

4. **Generation budget liberation**: Fix the hidden base.py max_tokens=256 hardcode to 512 (confirmed load-bearing from iter_004).

5. **Slightly softer abstention prompt**: Change "If the context does not contain the answer, say unknown" to "If the context is insufficient, answer unknown" to reduce over-abstention when evidence is present but scattered.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_005/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_005/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_005/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 16259 characters

