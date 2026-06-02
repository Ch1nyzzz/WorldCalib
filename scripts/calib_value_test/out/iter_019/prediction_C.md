# iter_019 prediction

## Candidate
list_block_extraction_from_long_docs

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, adaptive limits, sentence compression, 1024-token budget, minimal prompt) and replaces the brittle ratio-based list-preservation heuristic with a targeted list-block extraction mechanism. Inside `_compress_hit`, when a document is too long for short-list preservation (>8 units), the new code detects contiguous list blocks (2–6 items), scores them by query relevance, extracts the best block plus ±1 context unit, and bounds the extracted text to `max_sentences + 1` units. This fixes the 8cf51dda regression (3 objectives embedded in a 14-unit grant document) while avoiding the context-budget regressions that iter_018’s `len(units) <= 12` threshold caused.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.07] (from iter_018’s 0.64 to ~0.69–0.71)
- Failure type movement: The ~5 tasks that regressed from iter_016→iter_018 due to context-budget pressure (e.g., 07741c44, 099778bb) should return to passing. The 8cf51dda regression should flip from fail to stable_pass. Persistent_fail count should drop from ~35 to ~29–30. Wrong-answer and empty-prediction clusters should stay flat relative to iter_016.
- Trace movement: For previously regressed tasks, retrieved context should again contain the same high-relevance hits as in iter_016. For 8cf51dda, the context should show the complete 3-item objectives list instead of a truncated/reordered 2-item version. Average prompt tokens should stay near iter_016’s ~1807 level, not spike.
- Side effects to watch: The `max_sentences + 1` bounding is designed to prevent context-bloat, but if implementation bugs loosen the bound, token consumption could rise and push out tail hits. Also watch whether list-block detection misfires on non-list numbered sequences (e.g., years, counts) and causes accidental truncation of narrative context.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or corrupted (same failure mode as iter_018).
- If wrong-answer count rises above iter_016’s baseline (~6/100), the list-block extraction is surfacing noisy or conflicting list content from lower-relevance hits.
- If the 5 tasks that passed in iter_016 but failed in iter_018 remain failed, the `max_sentences + 1` bounding is still consuming too much context budget for those tasks.
- If 8cf51dda remains failed, the list-block detection is not correctly identifying the numbered objectives list within the grant document.
