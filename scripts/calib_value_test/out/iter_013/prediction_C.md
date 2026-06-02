# iter_013 prediction

## Candidate
multi_granularity_adaptive_retrieval

## Mechanism
The dominant failure family in iter_012 is retrieval misses: the gold answer is absent from all retrieved hits in roughly 30 of 43 failures. The new mechanism adds turn-level archival indexing alongside chunk-level passages, runs four-pass retrieval (BM25+cosine on both indexes with full and keyword-only queries), fuses rankings with RRF, and scales retrieval limits with sqrt(corpus size) instead of fixed top_k. This directly increases recall for large conversations and reduces relevance dilution when a relevant turn shares a chunk with irrelevant neighbors.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.61–0.67)
- Failure type movement: The retrieval-miss cluster should shrink by 6–12 tasks, converting persistent fails into breakthroughs. Tasks like 10d9b85a (April workshops) and 129d1232 (charity total) are high-probability fixes because keyword-only queries and turn-level indexing surface scattered mentions. Wrong-answer count should drop slightly as more complete evidence reaches the model. Empty predictions should stay flat or rise by at most 1 (the 1024-token budget and minimal prompt from iter_012 are preserved).
- Trace movement: Average retrieved count per task should rise from ~15 to ~20–25, with a larger share coming from archival memory. Traces should show more "turn"-tagged passages and broader coverage of large conversations. Top-hit relevance should improve for tasks where the gold was previously ranked outside the fixed top_k window.
- Side effects to watch: Token consumption will rise modestly because more candidates are retrieved, but sliding-scale compression (5/3/2 sentences) caps the growth. Risk of regressions is low because RRF fusion is robust and top hits still receive generous compression budgets, but 1–2 previously correct tasks could regress if keyword queries boost noisy passages into the top ranks.

## Falsification
- If passrate does not improve or regresses, the four-pass RRF fusion is either too noisy (keyword queries surfacing irrelevant docs) or the sliding compression on ranks 6+ is dropping critical evidence before the model sees it.
- If empty predictions rise above 4, the larger retrieval pool is overwhelming the model despite the minimal prompt; this would suggest a context-length or attention-dilution issue.
- If retrieval-miss tasks like 1a1907b4 (cocktail suggestions) and 10d9b85a (April workshops) remain failed with the same irrelevant top hits, the turn-level index and keyword queries are not helping semantic-mismatch cases, and the benefit is limited to lexical-surface fixes.
