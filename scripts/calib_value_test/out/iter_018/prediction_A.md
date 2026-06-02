# iter_018 prediction

## Candidate
contiguous_list_block_preservation

## Mechanism
Iter_017 catastrophically regressed from 0.69 to 0.17 because it applied the abstention-retry mechanism on top of the clean source snapshot without re-applying iter_016's load-bearing retrieval improvements (multi-granularity indexing, multi-signal fusion, adaptive limits, sentence compression, 1024-token budget). This candidate first restores the full iter_016 proven stack, then replaces the brittle ratio-based list-preservation heuristic (`list_markers >= len(units) * 0.5`) with contiguous list-block detection. The ratio-based approach fails when background prose dilutes the list ratio below 50%, causing structured answers (numbered objectives, bottle lists, DIY steps) to be compressed and reordered, destroying the structure the model needs. Contiguous-block detection looks for runs of 2+ consecutive list-marker lines and preserves the complete hit whenever such a block exists and the total unit count is reasonable (≤12). This is more robust because it depends on local structural contiguity, not global statistics, so embedding prose cannot hide a list block.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.05] (to ~0.71–0.74)
- Failure type movement: The list-truncation regression cluster (8cf51dda, 3249768e, 8aef76bc) should shrink from ~3 failures to ~0–1. The unknown/abstain cluster should stay flat or shrink by 1–2 if list-preservation also fixes synthesis failures on other list questions. Wrong answers should stay flat (~6). Empty predictions should stay at ~1.
- Trace movement: For previously failed list questions, the retrieved context should show complete list blocks instead of truncated/reordered sentences. No change in prompt length or format.
- Side effects to watch: Preserving complete list blocks in a few hits could consume slightly more context budget, potentially pushing out 1–2 tail hits for some tasks. The 8000-char limit and sliding-scale compression (5/3/2 sentences) should absorb this without major regressions.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or some other load-bearing component was lost in the patch application.
- If wrong-answer count rises, the list preservation is bringing in noisy/conflicting list content from lower-relevance hits.
- If empty predictions increase, the patch application inadvertently altered the prompt or model parameters (max_tokens, reasoning fallback).
