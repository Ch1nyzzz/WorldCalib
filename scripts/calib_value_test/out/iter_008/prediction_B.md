# iter_008 prediction

## Candidate
keyword_augmented_dual_pass_retrieval

## Mechanism
Restore the iter_006 scaffold stack (compact formatting, score calibration, contiguous window compression, 512-token generation budget, reasoning_content fallback) and add three mechanisms on top: (1) keyword-augmented dual-pass retrieval — for each tier, run the hybrid ranker once with the full query and once with stopwords removed, then fuse with RRF — to reduce stopword dilution and surface docs that match content words but not full phrasing; (2) focal sentence highlighting (wrapping the peak-relevance sentence in `** **` inside each compressed hit) to increase salience of answer-bearing regions; (3) a softened system prompt that explicitly permits synthesis across passages and restricts abstention to cases where no relevant information is present.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.07] (from iter_006 baseline of 0.50, so predicted passrate ~0.52–0.57)
- Failure type movement: The unknown/abstain cluster should shrink modestly (3–7 tasks) because dual-pass retrieval recovers some gold-bearing docs that the full-query ranking missed, and the softer prompt reduces unnecessary abstention when evidence is present. The wrong-answer cluster may grow slightly (+1 to +3 tasks) because the more permissive synthesis instruction increases the risk of hallucination or over-aggregation on tasks with conflicting or incomplete evidence. The empty-prediction cluster may grow by 1–3 tasks because `** **` highlighting has been observed to trigger hidden thinking in Qwen3, consuming generation budget.
- Trace movement: Retrieval traces should show additional docs surfacing in the top-8 that were previously outside the pool, particularly for queries with heavy stopword load (e.g., personal pronouns, auxiliary verbs). Context traces should show `** ... **` markers around peak sentences in compressed hits. Completion traces for some tasks may show empty content with reasoning_content fallback activated.
- Side effects to watch: (a) Tier sort changed from `(priority, score)` to `(score, priority)` — this may demote core memory on tasks where it is the primary evidence source, causing regressions. (b) The `**` highlighting interacts with Qwen3's chat template; even with the 512-token budget and reasoning_content fallback, hidden thinking could still truncate the visible answer. (c) Prompt softening risks converting previously-abstained tasks into wrong answers rather than correct ones.

## Falsification
- If train passrate drops below 0.50, the mechanism is net harmful. The most likely culprits would be the `**` highlighting triggering hidden-thinking truncation, or the tier-sort change demoting core memory, or the prompt softening causing synthesis errors on tasks that iter_006 passed.
- If the unknown cluster does not shrink (i.e., the number of "unknown" predictions stays at ~32), then dual-pass retrieval is not effective at recovering missed gold docs on this split, and the primary failure family remains unaddressed.
- If the empty-prediction cluster grows by more than 3 tasks, then `**` highlighting is a stronger negative lever for Qwen3 than the reasoning_content fallback can compensate for.
- If the wrong-answer cluster grows by more than 3 tasks, the softer prompt is causing harmful hallucination/aggregation errors that outweigh its abstention-reduction benefit.
