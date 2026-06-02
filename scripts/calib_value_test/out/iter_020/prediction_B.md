# iter_020 prediction

## Candidate
multi_objective_compression_with_answer_type_scoring

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, adaptive limits, sentence compression, 1024-token budget, minimal prompt). Replaces single-objective cosine compression in `_compress_hit` with a multi-objective score (0.65 query-relevance cosine + 0.35 answer-type likelihood heuristics). The answer-type scorer boosts sentences containing numbers for quantitative questions, dates/time words for temporal questions, yes/no markers for binary questions, and list markers for enumeration questions. Compressed units are joined with newlines instead of spaces to preserve list structure and sentence boundaries.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.70–0.72)
- Failure type movement: The list-truncation regression cluster (8cf51dda — grant objectives compressed from 3 to 2 items) should convert from fail to pass due to list-marker boosting and newline preservation. A subset of the unknown/abstain cluster — specifically quantitative and temporal synthesis failures where evidence is present in retrieved docs but the answer-bearing sentence was buried by pure cosine scoring (e.g., 7405e8b1 UberEats discount) — should shrink by 2–4 tasks. Wrong-answer count should stay flat (~6) or rise by at most 1, because the 0.35 answer-type weight is moderate and does not override relevance. Empty predictions should stay flat (~1).
- Trace movement: For 8cf51dda, the compressed top hit should now contain all three numbered objectives on separate lines instead of a truncated prose blob. For quantitative/temporal tasks, traces should show answer-bearing sentences (containing numbers, dates, or currency) appearing in the compressed context where they were previously dropped.
- Side effects to watch: Token consumption should remain unchanged because `max_sentences` budgets are identical. No prompt complexity was added, so empty-output risk from Qwen3 hidden thinking should not increase. The primary risk is that answer-type heuristics occasionally boost an irrelevant sentence containing a number/date/list marker and displace a genuinely relevant sentence within the same hit, but the 0.65 relevance weight limits this.

## Falsification
- If passrate does not reach at least 0.70, the answer-type signal is too weak to surface answer-bearing sentences within hits, or the iter_016 stack restoration was incomplete.
- If wrong-answer count rises by more than 1, answer-type scoring is systematically surfacing pattern-matching but irrelevant sentences (e.g., numbers from unrelated contexts), degrading synthesis quality.
- If empty predictions increase, the mechanism inadvertently altered model-call parameters or prompt length despite the stated restoration.
