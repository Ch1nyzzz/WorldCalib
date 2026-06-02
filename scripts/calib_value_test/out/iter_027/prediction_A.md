# iter_027 prediction

## Candidate
mmr_diversity_rerank_2048

## Mechanism
Add Maximal Marginal Relevance (MMR) diversity reranking to the retrieval pipeline in memgpt_scaffold.py. After multi-signal fusion produces an initial ranking for archival and recall tiers, MMR selects the final top-k docs by balancing relevance against pairwise cosine similarity. This reduces redundancy in the retrieved context (e.g. multiple generic charity-tip docs crowding out a specific bake-sale doc) and surfaces evidence that covers different aspects of the query. The generation budget is raised from 1536 to 2048 tokens as a supporting countermeasure for the small empty-output cluster caused by Qwen3 hidden thinking.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] from 0.69 to ~0.70–0.73
- Failure type movement: The aggregation and scattered-evidence persistent-fail subset (e.g. 129d1232 charity total, 10d9b85a April days) should shrink as MMR brings diverse relevant docs into the context window. The empty-output cluster (gpt4_21adecb5, gpt4_7abb270c) should shrink or convert to correct/unknown thanks to the larger token budget.
- Trace movement: Diagnostic traces should show more heterogeneous top-hit content for questions that previously had redundant top docs. The breakthrough count should exceed the regression count.
- Side effects to watch: Average token consumption will rise modestly (only for tasks that actually use >1536 tokens). Prompt wording and complexity are unchanged, so Qwen3 hidden-thinking risk stays low. Wrong-answer rate should not increase because MMR does not inject noise into the prompt.

## Falsification
- Passrate stays flat or drops (would refute the hypothesis that redundancy reduction improves coverage).
- The empty-output cluster does not shrink despite 2048 tokens (would indicate the bottleneck is reasoning architecture, not budget).
- Wrong-answer count rises by >3 (would indicate MMR is surfacing contradictory or noisy docs).
