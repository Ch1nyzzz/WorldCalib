# iter_028 prediction

## Candidate
answer_type_boost_aggregation

## Mechanism
Add answer-type-aware boosting to the retrieval ranking and adaptive MMR/synthesis for aggregation queries.

1. **Retrieval boosting**: After multi-signal fusion, docs that contain the expected answer type (numbers for "how much/many", dates for "when/how long", yes/no for boolean queries, list markers for enumeration queries) receive a small score boost. This helps surface evidence that is semantically relevant but lexically mismatched.

2. **Adaptive MMR for aggregation**: When aggregation signals are detected ("total", "all", "how many", "sum", "combined", "every", "each", "list"), the MMR candidate pool expands from k*3 to k*4 and lambda drops from 0.9 to 0.8, trading a small amount of relevance for more diversity. This brings scattered evidence into the context window.

3. **Aggregation synthesis hint**: For aggregation queries, the system prompt includes a one-line note: "When the question asks for a total, count, or list, carefully review all retrieved entries and combine the relevant facts before answering." This directly addresses synthesis failures where evidence is present but the model only uses a subset.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] from 0.71 to ~0.72–0.74
- Failure type movement: The partial-aggregation/wrong-answer cluster (10d9b85a, a08a253f, 852ce960, gpt4_2f91af09) should shrink by 2–4 tasks. The retrieval-miss cluster may also shrink slightly if answer-type boosting surfaces previously buried docs (129d1232, a08a253f). Unknown cluster should stay flat or shrink by 1–2.
- Trace movement: Diagnostic traces for aggregation tasks should show more diverse top-hit content. Model completions for aggregation tasks should show explicit combining language ("and", "total", "altogether").
- Side effects to watch: Token consumption may rise modestly because aggregation queries will see slightly more hits in context (pool expansion but same final k). Wrong-answer count should not rise because the boost only affects ranking, not answer injection. Empty outputs should remain at 0.

## Falsification
- Passrate stays flat or drops (would refute the hypothesis that answer-type boosting and aggregation tuning improve coverage/synthesis).
- Wrong-answer count rises by >2 (would indicate the boost is surfacing contradictory or noisy docs).
- Empty outputs reappear (would indicate the aggregation prompt instruction triggers Qwen3 hidden thinking).
