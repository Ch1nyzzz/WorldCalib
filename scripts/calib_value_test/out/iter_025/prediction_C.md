# iter_025 prediction

## Candidate
adjacent_archival_merge_1536

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, tiered compression, simplified formatting) and add two interacting changes:
1. Post-retrieval adjacency merging: archival hits with overlapping or contiguous turn_indices are merged into a single hit before deduplication, undoing harmful chunking fragmentation.
2. Increase generation budget from 1024 to 1536 tokens to eliminate empty outputs caused by Qwen3 hidden thinking consuming the full budget, plus fallback to reasoning_content if visible content is empty.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from iter_020 baseline of 0.69 to ~0.70–0.73)
- Failure type movement: Empty-output cluster should drop from 4 tasks to 0–1 due to the 1536-token ceiling and reasoning_content fallback. Wrong-answer cluster (e.g., charity total, antique count, museum order) may shrink by 1–2 tasks if adjacency merging surfaces complete list/numerical context that fragmented chunks previously split. Unknown/abstain cluster should stay roughly stable.
- Trace movement: Traces should show fewer truncated or blank predictions on tasks that previously exhausted the 1024-token budget. Archival hits in retrieval traces should show merged turn ranges (metadata.merged_from > 1) and longer contiguous text blocks, with reduced redundancy from overlapping chunk/turn passages.
- Side effects to watch: Average completion tokens per task may rise by 50–100 as the model no longer hits the 1024 limit. Prompt token consumption should stay similar because merged hits replace multiple redundant hits without increasing total context budget. Risk of regression is low because the proven iter_020 compression and ranking are preserved unchanged.

## Falsification
If passrate does not exceed iter_020’s 0.69, then either (a) the 1536-token budget does not help Qwen3 produce more correct answers beyond avoiding empties, or (b) adjacency merging hurts diversity enough to offset any gains from reduced fragmentation. If empty outputs persist at >1 task, the generation budget increase or reasoning_content fallback is ineffective for this model. If wrong-answer count does not shrink, fragmentation was not the cause of aggregation failures and the missing evidence is a retrieval-rank issue instead.
