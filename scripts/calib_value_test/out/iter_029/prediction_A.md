# iter_029 prediction

## Candidate
temporal_date_boost

## Mechanism
Restore the proven iter_027 stack (multi-signal retrieval, MMR diversity reranking, 2048-token generation budget, sentence compression, adjacent archival hit merging) and add a single new retrieval-side mechanism: temporal date-aware boosting. After multi-signal fusion and before MMR selection, docs whose dates match temporal expressions in the query (month names, years) receive a small relevance boost. This targets retrieval misses where the query references a specific time period but semantically similar docs from other periods outrank the gold docs (e.g., 10d9b85a where May docs outranked April docs for an April query).

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from 0.71 to ~0.72–0.74
- Failure type movement: The retrieval-miss cluster should shrink by 2–4 tasks, especially temporal-mismatch cases (10d9b85a, possibly 129d1232). The unknown cluster should drop slightly. Wrong-answer count should stay flat or drop by 1.
- Trace movement: Diagnostic traces for temporal queries should show top hits from the correct month/year. No change in prompt length or completion patterns.
- Side effects to watch: Token consumption should stay flat (retrieval-tier only). No risk of empty outputs because prompt is unchanged. Risk of query drift if a query mentions a date in a non-temporal sense (e.g., "What did I do before April?"); the small boost magnitude (0.10 for month, 0.05 for year) should not overwhelm strong lexical matches.

## Falsification
- Passrate stays flat or drops below 0.71 (would refute the hypothesis that temporal boosting improves retrieval coverage).
- Wrong-answer count rises by >2 (would indicate the boost is surfacing contradictory or noisy docs from the wrong period).
- Empty outputs reappear (would indicate an unintended prompt change; but this candidate does not touch the prompt).
