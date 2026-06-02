# iter_024 prediction

## Candidate
dynamic_contiguous_compression_top8

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, 1536-token generation budget, simplified formatting) and replace its fixed tiered compression with two interacting runtime changes: (1) dynamic relevance-proportional sentence allocation giving high-scoring hits up to 7 sentences and low-scoring hits 2 sentences, and (2) contiguous-window compression that finds the highest-scoring sentence in each hit and preserves a contiguous window around it instead of globally sorting sentences and taking the top-k.

## Outcome prediction
- Train passrate Δ: [+0.00, +0.03] (from iter_020's 0.69 to ~0.69–0.72)
- Failure type movement: Wrong-answer cluster should shrink by 1–2 tasks (contiguous windows preserve list/numerical context around answer-bearing sentences, e.g., charity totals, workshop counts, team-size enumerations). Unknown/abstain cluster stable or shrinks by 1 task. Empty-output cluster likely stable because those 4 tasks appear to be model-generation issues rather than compression issues.
- Trace movement: Compressed hits in traces should show contiguous sentence blocks instead of globally scattered high-scoring sentences. Top hits should retain 6–7 sentences (vs 5 in iter_020). Some previously wrong answers should now show complete multi-item lists or full numerical contexts.
- Side effects to watch: Average token consumption may rise by ~30–60 tokens per task because dynamic allocation can give top hits 7 sentences instead of the fixed 5 in iter_020. Risk of regression on 1–2 tasks where global sorting was actually better at extracting high-signal sentences from different parts of a long hit.

## Falsification
If the wrong-answer count does not shrink, the contiguous-window hypothesis is wrong for this dataset and local coherence does not help synthesis. If passrate drops below 0.69, the interaction between dynamic allocation and contiguous windows is harmful relative to the fixed tiered + global-sort baseline. If empty outputs increase, the longer contiguous blocks are confusing the model or pushing it over a hidden reasoning budget.
