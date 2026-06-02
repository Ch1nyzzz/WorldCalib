# iter_009 prediction

## Candidate
cross_hit_evidence_distillation

## Mechanism
The dominant failure families in iter_008 are (1) empty/truncated outputs caused by Qwen3 consuming the 512-token budget in hidden thinking, and (2) synthesis failures where the answer is present in retrieved docs but buried or scattered across long passages.

The new candidate layers two changes on top of the proven dual-pass retrieval, score calibration, and formatting from iter_008:

1. **Simplified direct-answer prompt**: Replace the verbose iter_008 prompt with a concise instruction that explicitly forbids step-by-step reasoning and demands an immediate answer. This reduces hidden thinking that consumes completion tokens.

2. **Cross-hit evidence distillation**: Before assembling the context, score every sentence in every retrieved hit by cosine similarity to the query. Extract the top-N highest-scoring sentences across all hits and present them as "Relevant excerpts" at the very top of the prompt, with inline provenance (which hit each sentence came from). The full compressed hits follow below. This front-loads the most answer-bearing evidence, reducing the cognitive load on the model and making it less likely to miss scattered facts or run out of tokens while reasoning.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.57–0.63)
- Failure type movement: The empty-prediction cluster should shrink from 10 to 2–4. The "unknown despite relevant docs" synthesis cluster should shrink because scattered evidence is surfaced prominently. Wrong-answer count should stay flat or rise slightly (risk of over-reliance on excerpts).
- Trace movement: Retrieved documents should show the same dual-query fusion. Spans should show a new "excerpts" section in the prompt with cross-hit provenance.
- Side effects to watch: Token consumption may rise slightly because we present both excerpts and full hits; completion tokens should drop because the model reasons less. Risk of regressions on tasks where full narrative flow matters more than individual sentences.

## Falsification
- If passrate does not improve or regresses, the cross-hit distillation may be adding noise rather than signal, or the simplified prompt may be too terse and cause more abstentions.
- If empty predictions stay at ~10, the issue is not prompt verbosity but a deeper serving-layer bug with Qwen3 thinking tokens, and the prompt change was ineffective.
- If the "unknown" cluster stays flat while empty predictions drop, the remaining unknowns are genuine retrieval misses and distillation cannot compensate.
