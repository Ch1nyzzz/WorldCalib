# iter_011 prediction

## Candidate
fixed_window_list_skeleton_highlighting

## Mechanism
Reverts from iter_010's proportional context allocation and answer-type boosting back to the proven iter_008 stack (fixed 5-sentence contiguous window + `**` peak-sentence highlighting, concise prompt, 512-token budget, dual-pass keyword-augmented retrieval). Adds one new compression rule: when a hit contains list items (numbered/bulleted/labeled), the complete list skeleton is preserved by truncating each item to its heading/first 10 words rather than dropping whole items or cutting mid-description. Non-list content falls back to the fixed 5-sentence window.

The mechanism targets the list-truncation-induced abstention family observed in iter_008/010: when compression cuts a numbered list after the first few items, the model sees an incomplete list and answers "unknown." This specifically should recover 3249768e (cocktail fifth bottle, failed in iter_008/010) and 8cf51dda (endometrial cancer objectives, regressed in iter_010). It should not affect tasks without list-bearing hits.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.54–0.56)
- Failure type movement: The unknown/abstain cluster should shrink by 2–4 tasks (list-truncation fixes for 3249768e and 8cf51dda, plus any other list-bearing persistent fails). Empty predictions should stay flat at ~3–5 (same concise prompt and 512-token budget as iter_008). Wrong-answer count should stay flat or rise by at most 1.
- Trace movement: Retrieved context for list-bearing hits should show all list items with truncated headings (e.g., "1. Sweet Vermouth ... 5. Absinthe ...") instead of mid-list cuts. Peak sentences should be wrapped in `**`. Non-list hits should show fixed 5-sentence windows.
- Side effects to watch: Token consumption should be similar to iter_008 (~1600 avg, lower than iter_010's ~1540 because proportional allocation is removed). Risk of context-budget regressions is low because list items are capped at 10 words each, but if a hit contains many list items it could crowd out later hits.

## Falsification
- If passrate does not improve or regresses, list skeleton preservation either fails to fix the target tasks (e.g., the relevant list is still truncated by sentence-splitting heuristics) or causes regressions by expanding list-bearing hits and dropping other evidence.
- If the unknown cluster stays flat while the target tasks remain in persistent_fail, the list-truncation diagnosis is wrong and the abstention is caused by something else (retrieval miss or prompt conservatism).
- If empty predictions rise above ~5, the `**` highlighting or list-preservation logic is triggering Qwen3 hidden thinking, indicating the prompt tier is not as safe as iter_008.
