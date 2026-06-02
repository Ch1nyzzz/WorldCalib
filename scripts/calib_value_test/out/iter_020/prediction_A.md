# iter_020 prediction

## Candidate
multi_objective_compression_with_answer_type_scoring

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, multi-granularity archival, adaptive limits, 1024-token budget, minimal prompt). Replaces the single-objective sentence compression in `_compress_hit` with a multi-objective score that combines (0.65) query-relevance cosine similarity with (0.35) answer-type likelihood heuristics. The answer-type scorer boosts sentences that contain numbers for quantitative questions, dates/time words for temporal questions, yes/no markers for binary questions, and list markers for enumeration questions. This surfaces answer-bearing content that pure relevance scoring buries. Additionally, compressed units are joined with newlines instead of spaces to preserve list structure and sentence boundaries.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (to ~0.70–0.73)
- Failure type movement: The synthesis-failure cluster (unknown despite evidence) should shrink by 2–4 tasks because answer-bearing sentences are more likely to survive compression. The list-truncation regression (8cf51dda) should convert to pass because list-item scores are boosted and newlines preserve structure. Retrieval misses (~13 tasks) should stay flat. Wrong-answer count should stay flat or rise by at most 1.
- Trace movement: For list-seeking questions, compressed context should show complete list items rather than partial lists. For temporal/comparison questions, date-bearing and number-bearing sentences should appear higher in the compressed text.
- Side effects to watch: Answer-type boosting could occasionally surface an irrelevant number or list item in a tail hit, but the 0.65 relevance weight keeps topical relevance dominant. Empty predictions should not increase because prompt complexity is unchanged.

## Falsification
- If passrate does not recover to at least 0.69, the iter_016 stack restoration was incomplete or the multi-objective scoring introduced a bug.
- If wrong-answer count rises by more than 1, answer-type boosting is surfacing misleading evidence and the 0.35 weight is too high.
- If empty predictions increase, the model parameters or prompt were inadvertently altered.
