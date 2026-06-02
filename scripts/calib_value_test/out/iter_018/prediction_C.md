# iter_018 prediction

## Candidate
contiguous_list_block_preservation

## Mechanism
Restore the full iter_016 proven retrieval stack (multi-granularity indexing, multi-signal fusion, adaptive limits, sentence compression, 1024-token budget) and replace the brittle ratio-based list-preservation heuristic in `_compress_hit` with contiguous list-block detection. The ratio heuristic (`list_markers >= len(units) * 0.5`) fails when background prose dilutes the list ratio below 50%, causing structured answers to be compressed and reordered. The new mechanism looks for runs of 2+ consecutive list-marker lines and preserves the complete hit whenever such a block exists and total units are ≤12. This is a local-structure cue that is insensitive to global prose dilution.

## Outcome prediction
- Train passrate Δ: [+0.52, +0.54] from iter_017 (absolute ~0.69–0.71)
- Failure type movement: The catastrophic unknown/abstain cluster that dominated iter_017 (83 persistent fails) should collapse back to roughly iter_016 levels (~30 persistent fails) because the load-bearing retrieval infrastructure is restored. The list-related partial-answer regression `8cf51dda` (grant objectives — model found 2 of 3 in iter_016, 0 of 3 in iter_015) should flip from fail to pass, shrinking the partial-answer/wrong-answer cluster by 1.
- Trace movement: For `8cf51dda`, the prediction should contain all three grant objectives in order rather than omitting the first. For the majority of previously-failed tasks, traces should resemble iter_016: evidence is retrieved and the model either synthesizes a concrete answer or abstains based on coverage, rather than uniformly abstaining due to missing retrieval.
- Side effects to watch: Average token consumption should jump from iter_017's ~1,023 back toward iter_016's ~1,807 because the full retrieval stack is restored. The list-block preservation may add a small additional token bump on hits with short list blocks, but the ≤12-unit cap limits it. Risk of regression on non-list tasks is low because the change is scoped to `_compress_hit` and only activates on contiguous list blocks.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or the source snapshot diverges from iter_016 in some load-bearing way.
- If passrate recovers to exactly 0.69 but not higher, the list-block fix did not save `8cf51dda` (likely because the source memory text is already truncated before `_compress_hit` runs, or because the model still fails to synthesize even when the full list is visible).
- If passrate exceeds 0.72, there were more list-block compression failures hidden in the persistent-fail set than the one known regression, and the contiguous-block mechanism saved additional tasks.
- If wrong-answer count rises relative to iter_016, preserving complete list hits with surrounding prose is introducing distracting context that pushes the model to hallucinate or mis-aggregate.
