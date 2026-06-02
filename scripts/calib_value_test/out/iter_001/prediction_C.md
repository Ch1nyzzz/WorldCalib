# iter_001 prediction
## Candidate
memgpt_source_compact_context

## Mechanism
Compress retrieved hit formatting (more compact core/archival/recall rendering, per-hit truncation in context packing) and strengthen the answer prompt to explicitly instruct the model to search all passages before answering unknown.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.25]         (baseline 0.16 → expected 0.26–0.41)
- Failure type movement: The dominant failure cluster — "unknown" answers when evidence is present in retrieved hits — should shrink by 30–50%. Context-truncation failures (where the answer sits in lower-ranked hits dropped by the old all-or-nothing cutoff) should nearly disappear. Pure retrieval-miss failures will persist unchanged.
- Trace movement: Average prompt tokens should rise from ~900 to ~1,500–2,500 because far more hits fit into the 6,000-char budget. Fewer traces will end with "FINAL ANSWER: unknown"; more will show quoted context snippets before the final answer. The number of hits visible in the context span should increase from ~2–3 to ~8–12.
- Side effects to watch: Token consumption will grow modestly but should stay well below context limits. The explicit "quote the relevant part" wording could occasionally produce verbose answers, though the preserved "FINAL ANSWER: <answer>" guard should keep judge extraction stable. The switch from tier-priority to score-priority deduplication sorting is unlikely to regress already-correct tasks because high-scoring archival/recall hits are typically the answer-bearing ones.

## Falsification
- If passrate stays below 0.22, the mechanism is weaker than expected — likely because retrieval misses (not context truncation) are the primary bottleneck, or the prompt change is insufficient to overcome the model's conservatism.
- If the "unknown" rate does not drop below 60%, the prompt strengthening failed to change generation behavior.
- If average prompt tokens does not increase by at least 300, the compression did not meaningfully expand context coverage.
