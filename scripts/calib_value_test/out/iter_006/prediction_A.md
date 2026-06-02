# iter_006 prediction

## Candidate
contiguous_window_compression

## Mechanism
Replace iter_005’s destructive list-block preservation with bounded contiguous relevance windows.

1. **Calibrated retrieval scaffold** (re-applied from iter_004): Remove arbitrary score boosts on summary/core memory, normalize RRF scores to [0,1], sort hits by score-first then tier, compact archival/recall/core formatting, and truncate archival turns to 300 chars. This is load-bearing and must be in place before any model-layer change.

2. **Contiguous relevance-window compression** (new): For each retrieved hit, split content into sentences, score each by query cosine similarity, find the peak-scoring sentence, and keep a contiguous 4-sentence window centered on that peak (±1–2 sentences). Always preserve the metadata line. Maximum 5 sentences per hit. This bounds per-hit length tightly, avoids the context-bloat that caused iter_005’s regression, and preserves local coherence better than iter_004’s scattered top-4 selection.

3. **Synthesis-permissive prompt**: Replace the overly restrictive “use exact words / do not explain reasoning” formulation with explicit permission to combine facts across passages and perform simple arithmetic/comparison when the supporting facts are present. This targets the over-abstention cluster where evidence is present but the model refuses to synthesize.

4. **512-token generation ceiling** in base.py and model.py default, with reasoning_content fallback for Qwen3 empty-content responses.

## Outcome prediction
- Train passrate Δ: [+0.06, +0.12] (from iter_004’s 0.49 baseline to ~0.55–0.61)
- Failure type movement:
  - “unknown/empty” cluster shrinks by 6–10 (synthesis permission + coherent context windows reduce abstention)
  - “wrong_answer” cluster stable or shrinks slightly (contiguity preserves negation and modifier context)
  - No regressions from iter_004 (bounded windows prevent context bloat)
- Trace movement:
  - More predictions contain synthesized values (sums, differences, comparisons)
  - Completion tokens stable (~100–250)
  - Prompt tokens stable or slightly lower than iter_005 (no list-block bloat)
- Side effects to watch:
  - Risk of hallucination from synthesis permission (mitigated by “using only the retrieved memory” grounding)
  - Risk that peak-centered windows miss answers at the very start or end of a long hit (mitigated by always including metadata line)

## Falsification
- Passrate below 0.50 would mean contiguous-window compression is not better than iter_004’s scattered top-4, or the synthesis prompt causes hallucinations that outweigh gains.
- “unknown” cluster not shrinking would mean over-abstention is driven by retrieval misses, not synthesis reluctance.
- Regressions above 3 would indicate the windowing still drops critical evidence.