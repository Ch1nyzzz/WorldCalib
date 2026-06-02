# iter_028 prediction

## Candidate
answer_type_boost_aggregation

## Mechanism
Add answer-type-aware boosting to the retrieval ranking and adaptive MMR/synthesis for aggregation queries.

1. **Retrieval boosting**: After multi-signal fusion, docs that contain the expected answer type (numbers for "how much/many", dates for "when/how long", yes/no for boolean queries, list markers for enumeration queries) receive a small score boost (max +0.15). This helps surface evidence that is semantically relevant but lexically mismatched.

2. **Adaptive MMR for aggregation**: When aggregation signals are detected ("total", "all", "how many", "sum", "combined", "every", "each", "list"), the MMR candidate pool expands from k*3 to k*4 and lambda drops from 0.9 to 0.8, trading a small amount of relevance for more diversity. This brings scattered evidence into the context window.

3. **Aggregation synthesis hint**: For aggregation queries, the system prompt includes a one-line note: "When the question asks for a total, count, or list, carefully review all retrieved entries and combine the relevant facts before answering." This directly addresses synthesis failures where evidence is present but the model only uses a subset.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from the iter_027 baseline of 0.71 to ~0.72–0.74.
- Failure type movement: The aggregation-query failure subset (e.g. 129d1232 charity total, gpt4_2f91af09 writing pieces, 10d9b85a April days) should shrink by 2–4 tasks as adaptive MMR (k×4 pool, λ=0.8) brings scattered or missed evidence into context and the synthesis hint prompts the model to combine facts across hits. The dominant unknown/abstain cluster should shrink modestly. Wrong-answer count should stay flat or rise by at most 1.
- Trace movement: Diagnostic traces for aggregation queries should show more heterogeneous top-hit content (diverse docs rather than redundant charity-tip or joke docs). Breakthroughs should outnumber regressions.
- Side effects to watch: The substring-matching bug in `_is_aggregation_query` ("all" matches "volleyball", "each" matches "reach") means 4 non-aggregation tasks get the MMR/synthesis treatment; risk of regression on these is low but non-zero. Average token consumption may rise slightly for aggregation queries due to the larger MMR pool. Empty-output risk is minimal because the 2048-token budget and reasoning_content fallback are preserved from iter_027.

## Falsification
- Passrate stays flat or drops (would refute that diversity + synthesis helps aggregation queries).
- Wrong-answer count rises by >2 (would indicate MMR diversity is surfacing noisy or conflicting docs).
- Breakthrough count ≤ regression count (would indicate the mechanism is net-negative rather than net-positive).
