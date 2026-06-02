# iter_025 prediction

## Candidate
adjacent_archival_merge_1536

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, tiered compression, simplified formatting) and add two interacting changes:
1. Post-retrieval adjacency merging: archival hits with overlapping or contiguous turn_indices are merged into a single hit before deduplication. This reduces redundant chunking overlap and may free context budget for additional tail hits.
2. Increase generation budget from 1024 to 1536 tokens to eliminate the empty-output cluster caused by Qwen3 hidden thinking consuming the full budget.

## Outcome prediction
- Train passrate Δ: [−0.01, +0.02] (from 0.69 to ~0.68–0.71)
- Failure type movement:
  - Empty-output cluster drops from 4 to 0 (1536-token budget is load-bearing for this, confirmed by iter_024).
  - Unknown/abstain cluster stays roughly flat or shifts by ±1 (adjacency merge is retrieval-side and does not directly fix synthesis abstention; 1536 tokens converts empty→unknown but not empty→correct based on iter_024 evidence).
  - Wrong-answer cluster stays flat or grows by 1 (risk that merging overlapping archival chunks reduces total sentence budget for previously-passing structured-answer tasks like 8cf51dda, where multiple overlapping archival hits currently each contribute 2 sentences).
- Trace movement:
  - Zero predictions with 0 completion tokens; all tasks produce some output.
  - Fewer total hits in retrieved context because overlapping archival chunks merge; 1–2 additional tail recall hits may appear in context for some tasks.
  - Slight increase in average completion tokens (~1100 vs ~950) as the 4 previously-empty tasks now emit text.
- Side effects to watch:
  - Regressions in tasks where overlapping archival hits each previously contributed distinct relevant sentences (e.g., 8cf51dda grant objectives). Merging them into one hit with 2-sentence compression could drop critical list items.
  - No expected prompt-length increase because merging happens post-retrieval and compression bounds per-hit length.

## Falsification
If passrate drops below 0.67, adjacency merging is causing material regressions in list/structured answers by shrinking sentence budget for merged archival components. If passrate exceeds 0.72, the merge is uncovering significantly more gold-bearing evidence than expected, suggesting that context-budget freeing from redundancy removal is the dominant effect. If empty outputs persist at 1536 tokens, the generation-budget hypothesis for Qwen3 empty outputs is wrong.
