# iter_018 prediction

## Candidate
contiguous_list_block_preservation

## Mechanism
Iter_017 catastrophically regressed from 0.69 to 0.17 by building the abstention-retry mechanism on the clean source snapshot without re-applying iter_016's load-bearing retrieval improvements. This candidate first restores the full iter_016 proven stack (multi-granularity archival indexing, multi-signal hybrid ranking with bigram/char-ngram fusion, RRF-based ranking fusion, adaptive retrieval limits, sentence-level relevance surfacing, 1024-token generation budget, reasoning-content fallback), then replaces the brittle ratio-based list-preservation heuristic (`list_markers >= len(units) * 0.5`) with contiguous list-block detection. The new rule looks for runs of 2+ consecutive list-marker lines and preserves the complete hit without truncation or reordering whenever such a block exists and the total unit count is ≤12. This is more robust because it depends on local structural contiguity rather than global statistics, so embedding prose cannot hide a list block.

## Outcome prediction
- Train passrate Δ: [+0.50, +0.54] from iter_017's 0.17, to an absolute ~0.67–0.71. The central estimate is ~0.70 (restoring iter_016's 69 passes and recovering the one known regression 8cf51dda).
- Failure type movement: The persistent_fail cluster should collapse from ~83 tasks (iter_017) back to ~30 tasks (iter_016 level) as the retrieval stack is restored. The unknown/abstain cluster should shrink by ~1 task (8cf51dda moving from unknown to correct). Wrong-answer and empty-output clusters should remain stable at iter_016 levels (~6 wrong, ~1 empty).
- Trace movement: Retrieval scores for top hits should return to iter_016 levels (0.90+ cosine for relevant docs) instead of iter_017's broken retrieval (0.03–0.30). Prompt token counts should return to iter_016's range (~1400–1800 tokens). 8cf51dda should appear as a stable_pass or breakthrough instead of a regression.
- Side effects to watch: (1) The contiguous-block heuristic is slightly more permissive than the ratio heuristic for small embedded lists in long prose, which could increase average prompt length by 0–5% but should not blow the context budget because the condition is bounded (≤12 units). (2) If the restoration missed any load-bearing component from iter_016, the passrate could land below 0.65. (3) No Qwen3 empty-output spike is expected because the prompt and generation path are unchanged from iter_016.

## Falsification
- If train passrate is <0.65, the iter_016 stack restoration was incomplete or the list-block change introduced unexpected regressions.
- If 8cf51dda does NOT pass, the contiguous-block detection failed to preserve the objectives list or the retrieval stack was not fully restored.
- If empty predictions jump above 2 (iter_016 had ~1), the generation path was altered in a way that triggers Qwen3 hidden thinking.
- If wrong-answer count grows beyond iter_016's ~6, the list-block preservation is surfacing noisy or irrelevant structured content that confuses synthesis.
