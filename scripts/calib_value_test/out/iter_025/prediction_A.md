# iter_025 prediction

## Candidate
adjacent_archival_merge_1536

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, tiered compression, simplified formatting) and add two interacting changes:
1. Post-retrieval adjacency merging: archival hits with overlapping or contiguous turn_indices are merged into a single hit before deduplication. This undoes harmful chunking fragmentation and preserves complete conversational threads for aggregation questions.
2. Increase generation budget from 1024 to 1536 tokens to eliminate the empty-output cluster caused by Qwen3 hidden thinking consuming the full budget.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from 0.69 to ~0.70–0.73)
- Failure type movement: Empty-output cluster should shrink from 4 to 0. Wrong-answer cluster should shrink by 1–3 tasks (adjacency merging preserves complete numerical/list context that was split across archival chunks). Unknown cluster may stay flat or grow slightly if previously-empty tasks become unknown instead of correct.
- Trace movement: Fewer truncated or partial answers for counting/total questions. Merged archival hits should show `merged_from` metadata > 1 in traces.
- Side effects: Average prompt token consumption may rise slightly because merged archival hits are longer. Average completion tokens may rise because of the 1536 budget. No expected regressions because the mechanism only changes retrieval-tier hit grouping, not prompt wording or model behavior.

## Falsification
If passrate drops below 0.69, adjacency merging is actively hurting synthesis (e.g., by merging conflicting adjacent turns). If empty outputs persist at 1536 tokens, Qwen3 hidden thinking is not governed by generation budget alone. If wrong-answer count does not shrink, archival chunking fragmentation is not the root cause of under-counting.
