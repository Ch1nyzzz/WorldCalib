# iter_028 prediction

## Candidate
answer_type_boost_aggregation

## Mechanism
Add answer-type-aware boosting to retrieval ranking and adaptive MMR/synthesis for aggregation queries. After multi-signal fusion, docs containing the expected answer type (numbers for quantitative queries, dates for temporal queries, yes/no cues for boolean queries, list markers for enumeration queries) receive a small score boost. For aggregation queries detected by keyword phrases ("total", "how many", "how much", etc.), the MMR candidate pool expands from 3× to 4× and lambda drops from 0.9 to 0.8, trading a small amount of relevance for more diversity. The system prompt also gains a one-line synthesis hint for aggregation queries: "When the question asks for a total, count, or list, carefully review all retrieved entries and combine the relevant facts before answering."

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from 0.71 to ~0.72–0.74
- Failure type movement: The aggregation persistent-fail cluster (10d9b85a April workshops, 129d1232 charity total, and 1–2 others) should shrink as adaptive MMR surfaces scattered evidence and the synthesis prompt drives combination. Yes/no (0bc8ad93 museum friend) and recommendation (0edc2aef Miami hotel) persistent failures should remain stable. Numerical inference gaps (157a136e grandma age) should persist unless answer-type boosting serendipitously surfaces the missing fact.
- Trace movement: Retrieval traces for aggregation queries should show more heterogeneous top-hit content (different events/amounts/dates) compared to iter_027. Model completions for aggregation queries should increasingly contain explicit summation or enumeration language.
- Side effects to watch: Average token consumption should stay flat (~1830) because pool expansion is modest and the context budget is unchanged. Wrong-answer count should not rise by more than 1 because boosts are small and capped at 0.15.

## Falsification
- Passrate stays flat or drops (would indicate answer-type boosting either has no effect or actively surfaces misleading docs).
- The two clearest aggregation targets (10d9b85a and 129d1232) remain failed despite adaptive MMR and synthesis hint (would indicate the bottleneck is retrieval coverage or evidence missing from the corpus, not ranking/synthesis).
- Wrong-answer count rises by >2 (would indicate the lower MMR lambda for aggregation is injecting noise that confuses the model).
