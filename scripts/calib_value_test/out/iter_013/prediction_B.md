# iter_013 prediction

## Candidate
multi_granularity_adaptive_retrieval

## Mechanism
The dominant failure family is retrieval misses: 31 of 43 failures in iter_012 have the gold answer absent from all retrieved hits. The new mechanism attacks this with (1) turn-level archival indexing (chunk_size=1) alongside original chunks to reduce relevance dilution, (2) four-pass retrieval (BM25+cosine on both chunk and turn indexes with full and keyword-only queries) fused with RRF to increase surface area, (3) adaptive retrieval limits scaling with sqrt(corpus size) so large conversations fetch more candidates, and (4) sliding-scale compression (5 sentences for top 2, 3 for next 3, 2 for rest) to preserve context budget despite the larger pool. Load-bearing fixes from iter_012 are kept: 1024-token generation budget, reasoning_content fallback, minimal prompt, compact formatting, score-first tier sorting.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.61–0.67)
- Failure type movement: Retrieval misses shrink from ~31 to ~20–25. Empty predictions stay at ~2. Unknown/abstain shrink by 5–10 tasks. Wrong-answer count stays flat or rises by 1–2 as the larger pool introduces occasional conflicting evidence.
- Trace movement: Retrieval spans show more documents per task (adaptive limits). Some previously-missing gold-bearing docs surface via turn-level or keyword-only rankings. Compressed hits show sliding-scale sentence counts (5/3/2) instead of the prior two-tier scheme.
- Side effects to watch: Prompt tokens rise ~10–20% due to larger retrieval pools. Risk of 2–4 regressions on tasks where the gold hit was previously in tier-1 (minimal compression) but now ranks lower and gets more aggressively truncated.

## Falsification
- If train passrate does not exceed 0.59, the turn-level index failed to build or the four-pass fusion added noise without improving coverage, indicating a build or implementation issue.
- If empty predictions rise above 4, the prompt or generation budget was accidentally altered, contradicting the load-bearing assumption.
- If wrong-answer count rises sharply above 12, the larger retrieval pool is introducing noisy/conflicting evidence that outweighs the coverage gains.
