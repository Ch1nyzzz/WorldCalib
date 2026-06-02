# iter_027 prediction

## Candidate
mmr_diversity_rerank_2048

## Mechanism
Add Maximal Marginal Relevance (MMR) diversity reranking to the retrieval pipeline in memgpt_scaffold.py. After multi-signal fusion produces an initial ranking for archival and recall tiers, MMR selects the final top-k docs by balancing relevance against pairwise cosine similarity (lambda=0.9). This reduces redundancy in the retrieved context (e.g. multiple generic charity-tip docs crowding out a specific bake-sale doc) and surfaces evidence that covers different aspects of the query. The generation budget is raised from 1536 to 2048 tokens as a supporting countermeasure for the small empty-output cluster caused by Qwen3 hidden thinking.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from ~0.69 to ~0.70–0.73)
- Failure type movement: The unknown/abstain cluster should shrink slightly (MMR surfaces more diverse evidence, converting a few "context does not contain" synthesis failures into passes). The empty-output cluster should drop from ~1 task to ~0 (2048-token budget absorbs any remaining hidden-thinking truncation). Wrong-answer count should stay flat or decrease by 1–2 (better evidence coverage reduces undercounting on aggregation tasks like 129d1232).
- Trace movement: Retrieval top-k traces should show increased diversity — e.g., different charity events or workshop dates appearing instead of multiple near-duplicate generic tip docs. The persistent_fail tasks that break through will be primarily aggregation/list questions where redundant docs previously crowded out key evidence.
- Side effects to watch: Prompt token count may rise modestly if diverse docs are longer on average. MMR adds O(k²·n) compute but the candidate pool is capped at k×3 so runtime impact should be negligible. No API errors expected — the change is local to ranking and does not touch prompt construction or the model client beyond the token budget bump.

## Falsification
- Passrate stays at 0.69 or drops: would indicate that redundancy is not the actual bottleneck, or that lambda=0.9 is too conservative to reorder hits meaningfully.
- Empty outputs persist at ≥1 task: would indicate the 2048-token budget is still insufficient for Qwen3 hidden thinking on some task shapes.
- Wrong-answer count rises by ≥2: would indicate MMR is surfacing diverse but lower-relevance docs that confuse synthesis, contradicting the conservative lambda=0.9 design.
