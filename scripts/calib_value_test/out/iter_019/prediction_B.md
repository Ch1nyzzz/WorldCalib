# iter_019 prediction

## Candidate
list_block_extraction_from_long_docs

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, adaptive limits, sentence compression, 1024-token budget, minimal prompt) and replaces the brittle ratio-based list-preservation heuristic with targeted list-block extraction inside `_compress_hit`. For documents too long for short-list preservation (>8 units), the code detects contiguous list blocks (2–6 items), scores them by query relevance, and extracts the best block plus ±1 context unit, bounding total extracted text to `max_sentences + 1` units. This fixes 8cf51dda (3 objectives in a 14-unit grant document) without the context-budget regressions that iter_018’s `len(units) <= 12` threshold caused.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.70–0.72)
- Failure type movement: The list-truncation regression cluster (8cf51dda) should flip from fail to pass. The six context-budget regressions introduced in iter_018 (10d9b85a, gpt4_61e13b3c, 07741c44, 7405e8b1, 099778bb, 1f2b8d4f) should recover to their iter_016 pass state because per-hit length is now tightly bounded rather than expanded. The unknown/abstain cluster should stay flat or shrink by 1–2 if other list-structured questions (e.g., gpt4_7abb270c, gpt4_7f6b06db) also benefit. Wrong answers should stay flat (~6–8). Empty predictions should stay at ~1.
- Trace movement: For 8cf51dda, the retrieved context should show the complete 3-objective list block instead of truncated/reordered sentences. For long documents with embedded lists, traces should show compact extracted list blocks rather than full-document preservation. Prompt length and format should match iter_016.
- Side effects to watch: (1) The 29 kchar patch across 3 files creates implementation-risk; verify no hidden parameter changes (max_tokens, reasoning fallback). (2) If list-block detection misfires on non-list prose, it could drop important surrounding context for 0–1 tasks. (3) The ±1 context unit may be insufficient for list blocks that need surrounding explanatory prose to be interpretable.

## Falsification
- If passrate does not recover to at least 0.68, the iter_016 stack restoration was incomplete or the extraction mechanism introduced regressions.
- If wrong-answer count rises above 8, the list extraction is surfacing noisy or conflicting list content from lower-relevance hits.
- If empty predictions increase above 2, the patch inadvertently altered the prompt or model call parameters.
- If 8cf51dda still fails, the list-block detection or relevance scoring is missing the objectives block.
