# iter_024 prediction

## Candidate
dynamic_contiguous_compression_top8

## Mechanism
Restore the proven iter_020 stack (multi-signal retrieval, multi-granularity archival indexing, answer-type sentence scoring, 1024→1536 token generation budget, simplified formatting) and replace the fixed tiered compression (top-2 hits → 5 sentences, next-3 → 3, rest → 2) with two interacting runtime changes:
1. Dynamic relevance-proportional sentence allocation: each hit gets `max_sentences = max(2, min(7, int(2 + 5 * (hit.score / max_score) + 0.5)))`, giving high-scoring hits up to 7 sentences and low-scoring hits 2 sentences.
2. Contiguous-window compression: instead of globally sorting sentences by combined relevance+answer-type score and taking the top-k, find the single highest-scoring sentence in each hit and preserve a contiguous window around it. This keeps local context, list order, and sentence flow intact.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.06] (from 0.69 to ~0.71–0.75)
- Failure type movement: Wrong-answer cluster should shrink by 2–4 tasks (contiguous windows preserve complete numerical/list context that global top-k reordering drops). Empty-output cluster should shrink by 1–2 tasks due to the 1536-token ceiling. Unknown/abstain cluster may shrink by 1–2 tasks if better context preservation surfaces missed evidence.
- Trace movement: Fewer truncated lists and miscounted totals. More hits should retain complete local context around the answer-bearing region.
- Side effects to watch: Average prompt token consumption may rise by ~30–50 tokens per task because mid-ranked hits now get 3–5 sentences instead of a flat 2–3. No expected regressions because the mechanism only changes which sentences are kept, not prompt wording or retrieval logic.

## Falsification
If wrong-answer count does not shrink, contiguous-window preservation is not helping aggregation and the failure is either retrieval miss or model reasoning error. If empty outputs persist at 1536 tokens, Qwen3 hidden thinking is not governed by generation budget. If passrate drops below 0.69, the interaction between longer average contexts and Qwen3 synthesis is negative.
