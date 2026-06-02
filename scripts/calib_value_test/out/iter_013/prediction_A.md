# iter_013 prediction

## Candidate
multi_granularity_adaptive_retrieval

## Mechanism
The dominant failure family is retrieval misses: 31 of 43 failures in iter_012 have the gold answer string absent from all retrieved hits. Evidence source 1: task 1a1907b4 (cocktail suggestions) retrieves 12 docs about scented sprays and lens purchases; the mixology-class doc is missing. Evidence source 2: task 129d1232 (total charity raised) retrieves cycling tips and waste reduction; the docs with additional fundraising amounts are missing. Evidence source 3: task 10d9b85a (April workshop days) retrieves joke questions and theatre reviews; the April attendance doc is missing.

The new mechanism is multi-granularity archival indexing paired with adaptive retrieval limits:
1. **Turn-level archival passages** (chunk_size=1) are indexed alongside the original chunk passages. This reduces relevance dilution: a relevant turn is no longer penalized for sharing a chunk with irrelevant neighbors, so it can rank higher in sparse retrieval.
2. **Four-pass retrieval** runs BM25+cosine on both chunk and turn indexes with both the full query and a keyword-only (stopword-removed) query, then fuses the four rankings with RRF. This increases the chance that a relevant doc surfaces.
3. **Adaptive retrieval limits** scale with sqrt(corpus size) instead of fixed top_k fractions, ensuring large conversations retrieve more candidates.
4. **Sliding-scale compression** (5 sentences for top 2, 3 for next 3, 2 for rest) preserves context budget while fitting the larger pool.
5. **Load-bearing fixes kept**: 1024-token generation budget, reasoning_content fallback, minimal prompt, compact formatting, score-first tier sorting.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.61–0.67)
- Failure type movement: Retrieval misses should shrink by 5–10 tasks (turn-level indexing + larger pool bring more gold docs into context). Unknown/abstain should drop by 3–6 (many unknowns are actually retrieval misses). Empty predictions should stay at 0–2. Wrong answers might rise by 1–2 due to noise from larger pool.
- Trace movement: Retrieved hit count should increase (avg > 15). More retrieved docs should contain the gold string for previously missed tasks. Top hits remain well-formatted; lower hits are heavily compressed.
- Side effects to watch: Prompt tokens may rise ~10-20% due to larger retrieval pool. Risk of regression on tasks where the answer requires a contiguous multi-turn block that gets split across turn-level passages; chunk passages and recall window expansion still preserve blocks.

## Falsification
- If retrieval miss count does not drop below 25, the multi-granularity indexing is insufficient or the missed docs are ranked extremely low for other reasons (vocabulary mismatch).
- If passrate does not improve or regresses, the added noise from larger pool or turn-level splitting hurts synthesis more than retrieval gains.
- If empty predictions rise above 4, the prompt/context changes re-introduced hidden-thinking triggers.
