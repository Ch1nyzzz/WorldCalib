# iter_027 prediction

## Candidate
mmr_diversity_rerank_2048

## Mechanism
Add Maximal Marginal Relevance (MMR) diversity reranking (λ=0.9, pool=3×k) to both archival and recall retrieval tiers in memgpt_scaffold.py, plus raise the generation max_tokens budget from 1536 to 2048 in base.py/model.py.

MMR penalises pairwise token-cosine similarity among selected docs. With λ=0.9 the mechanism is conservative: it preserves high-relevance docs and only swaps out nearly-redundant siblings for moderately diverse alternatives. This should reduce the extreme redundancy clusters observed in the current persistent failures (e.g. 5–7 top-k docs coming from the same conversation turn) and free 1–2 slots for buried evidence from other turns.

The 2048-token budget is a safety net; iter_025 completions rarely exceeded 900 tokens, so the increase from 1536 is expected to affect only a tiny empty-output tail.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (new passrate 0.70–0.73)
- Failure type movement:
  - The "redundant-cluster-crowding" persistent-fail cluster should shrink by 2–4 tasks. These are tasks where the answer exists in the retrieval pool but is buried below a block of highly similar docs from the same timestamp (e.g. `0bc8ad93` museum friend with 7 docs from the same turn; `10d9b85a` April workshops with relevant docs at ranks 12–15).
  - Pure retrieval-miss tasks (e.g. `129d1232` charity total missing bake-sale evidence, `0edc2aef` Miami hotel missing entirely, `157a136e` grandma age missing user age) will remain failed.
  - The small empty-output cluster (~1 task in iter_025) may drop to 0 due to the token budget headroom.
- Trace movement:
  - Top-8 retrieved doc sets should show fewer instances of 5+ docs sharing the exact same `[Recall]` timestamp.
  - Newly-passed tasks should exhibit greater date-turn diversity in their final context while retaining their highest-relevance doc.
- Side effects to watch:
  - avg_token_consuming may rise slightly (+20–50) because a few completions that were near the old ceiling can now expand.
  - Minimal regression risk among stable passes: λ=0.9 always keeps the top-relevance doc, so tasks whose answer was already in rank 1 should not break.

## Falsification
- Passrate stays at 0.69 or drops: would mean MMR’s conservative λ=0.9 is too weak to surface useful buried docs, or that diversity hurts aggregation/temporal tasks more than expected.
- Redundancy counts in traces do not decrease: would indicate the MMR implementation is not being applied to the actual retrieval path used at runtime.
- Token consumption jumps by >200: would suggest the 2048 budget is causing the model to produce verbose, off-topic outputs that degrade answer precision.
