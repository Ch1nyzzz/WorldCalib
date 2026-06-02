# iter_009 prediction

## Candidate
cross_hit_evidence_distillation

## Mechanism
The candidate layers two changes on iter_008's proven dual-pass retrieval:

1. **Simplified direct-answer prompt**: Replaces the verbose iter_008 system prompt with a concise instruction that demands an immediate, concise answer. This targets the ~10 empty/truncated outputs in iter_008 where the model consumed the full 512-token budget without emitting usable content.

2. **Cross-hit evidence distillation**: Before packing context, scores every sentence in every retrieved hit by cosine similarity to the query, extracts the top-N highest-scoring sentences across all hits, and presents them as "Relevant excerpts" at the very top of the prompt with inline provenance. Full compressed hits follow below. This front-loads answer-bearing evidence, reducing the chance that the model misses scattered facts buried in long passages.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.10] (to ~0.58–0.63)
- Failure type movement: The empty/truncated-output cluster should shrink dramatically from ~10 cases to ~2–4. The "unknown despite relevant docs" synthesis cluster should shrink by ~4–6 cases as front-loaded excerpts make answer-bearing sentences salient. Wrong-answer count may rise slightly (+1 to +2) because the more direct prompt can rush to a conclusion on ambiguous passages.
- Trace movement: Spans should show "Relevant excerpts:" at the top of prompts. Completion tokens for previously empty cases should drop from 512 to well under the budget. More predictions should contain a non-empty FINAL ANSWER line.
- Side effects to watch: Prompt tokens may rise slightly (~100–200 avg) due to the excerpts block. Risk of regressions on multi-step temporal or arithmetic questions where the direct-answer prompt short-circuits necessary reasoning.

## Falsification
- If passrate does not improve or regresses, the sentence-extraction noise is outweighing signal, or the simplified prompt is causing harmful hallucination that erases the retrieval gains.
- If the empty-output cluster stays flat (~10 cases), the prompt change did not fix the underlying generation truncation issue.
- If wrong-answer count increases by more than 3, the direct-answer pressure is causing the model to guess rather than abstain, and the mechanism is net harmful.
