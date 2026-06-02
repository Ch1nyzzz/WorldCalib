# iter_011 prediction

## Candidate
fixed_window_list_skeleton_highlighting

## Mechanism
The dominant failure family is list-truncation-induced abstention: when proportional or fixed-window compression cuts off a numbered/bullet list after the first few items, the model sees an incomplete list and answers "unknown." This was observed in `3249768e` (gin cocktail bottles — passed only in iter_006 with fixed 5-sentence window, failed in all proportional/allocation iterations) and `8cf51dda` (endometrial cancer objectives — passed in iter_006/008 with fixed window or highlighting, failed in iter_009/010).

The new mechanism is a structure-aware compression function that:
1. Detects list blocks (numbered, bulleted, or labeled items) inside a retrieved hit.
2. When compressing a list-bearing hit, truncates each item to its heading/first sentence rather than dropping whole items or cutting mid-description. This preserves the complete list skeleton within the per-hit budget.
3. For non-list content, falls back to a fixed 5-sentence contiguous window around the most query-relevant sentence (proven in iter_006).
4. Wraps the peak sentence in `**` to guide the model's attention (observed to help in iter_008).

The prompt stays concise and direct (iter_006 style) to avoid Qwen3 hidden-thinking empty outputs. The 512-token generation budget is retained.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (to ~0.56–0.60)
- Failure type movement: The unknown/abstain cluster should shrink by 4–8 tasks (list-preservation fixes `3249768e`-style failures and focal highlighting reduces missed evidence). Empty predictions should stay at ~3–5 (simple prompt). Wrong-answer count should stay flat or rise by 1–2.
- Trace movement: Compressed hits should show complete list skeletons (e.g., "1. Sweet Vermouth... 2. Dry Vermouth... 3. Campari... 4. Elderflower... 5. Absinthe...") instead of truncated partial lists. Peak sentences should appear wrapped in `**`.
- Side effects to watch: Token consumption should stay similar to iter_006 (~160k) because list-skeleton truncation is aggressive on descriptions. Risk of regressions on tasks where verbose descriptions are needed to disambiguate list items.

## Falsification
- If passrate does not improve or regresses, the list-skeleton truncation may be too aggressive (dropping disambiguating description) or the fixed window may be too narrow for non-list answers.
- If empty predictions rise above 5, the `**` highlighting or list formatting may trigger hidden thinking in Qwen3.
- If the unknown cluster stays flat while list tasks don't improve, the remaining unknowns are genuine retrieval misses and compression cannot compensate.
