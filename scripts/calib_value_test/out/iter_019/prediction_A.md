# iter_019 prediction

## Candidate
list_block_extraction_from_long_docs

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, adaptive limits, sentence compression, 1024-token budget, minimal prompt) that achieved 0.69 passrate. Replaces the brittle ratio-based list-preservation heuristic (`_is_short_list`) with a targeted list-block extraction mechanism that operates inside `_compress_hit`. When a document is too long for the existing short-list preservation (><8 units), the new code detects contiguous list blocks (2–6 items), scores them by query relevance, and extracts the best block plus ±1 context unit. The extracted text is bounded to `max_sentences + 1` units, so it never consumes more context budget than normal compression and often consumes less. This fixes the 8cf51dda regression (3 objectives embedded in a 14-unit grant document) without the context-budget regressions that iter_018’s `len(units) <= 12` threshold caused.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.70–0.72)
- Failure type movement: The list-truncation regression cluster (8cf51dda) should convert from fail to pass. The unknown/abstain cluster should shrink by 0–1 if any other long-document list questions exist. Wrong answers and empty predictions should stay flat (~6 and ~1).
- Trace movement: For 8cf51dda, the compressed context should now show all three objectives instead of only two. No change in prompt length or format for other tasks.
- Side effects to watch: Extracting list blocks from long documents could occasionally displace a relevant prose sentence in the same hit, but the ±1 context window and `max_sentences + 1` bound limit this risk. Empty predictions should not increase because prompt complexity is unchanged.

## Falsification
- If passrate does not recover to at least 0.69, the iter_016 stack restoration was incomplete.
- If wrong-answer count rises, list-block extraction is including irrelevant list content and crowding out prose answers.
- If empty predictions increase, the model parameters or prompt were inadvertently altered.
