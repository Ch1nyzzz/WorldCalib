# iter_010 prediction

## Candidate
answer_type_boosted_retrieval_with_proportional_context

## Mechanism
The candidate layers two retrieval-side and context-packing changes on top of the proven dual-pass retrieval and simplified formatting from iter_006/008:

1. **Answer-type-aware retrieval boosting**: After dual-pass retrieval, detect the expected answer type from the question (numbers, dates, percentages, lists) using lightweight regex heuristics. Boost the scores of retrieved hits that contain matching patterns by 15%. This operates entirely in the retrieval tier without adding prompt complexity.

2. **Score-proportional context allocation**: Instead of compressing every hit to a fixed window, allocate the global `max_context_chars` budget proportionally to each hit's relevance score (minimum 200 chars floor). Within each budget, a contiguous window around the most query-relevant sentence is preserved. This ensures high-confidence evidence is shown in full while low-scoring hits are abbreviated.

The prompt is kept concise and direct (iter_006 style, no cross-hit excerpts) and the 512-token generation budget is retained to avoid Qwen3 hidden-thinking truncation.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.03] (to ~0.55–0.57)
- Failure type movement:
  - Empty-prediction cluster should shrink from ~10 (iter_009) to ~6–8 because the simpler prompt avoids triggering hidden thinking compared to iter_009's cross-hit excerpts.
  - Unknown/abstain cluster should shrink modestly (by ~2–4 tasks) because proportional allocation preserves more of the top hit's content, converting some synthesis failures where the answer was buried in a highly-ranked but truncated document.
  - Wrong-answer count should stay flat (~7–9) since the mechanism does not introduce new hallucination pressure.
- Trace movement:
  - Retrieved document lists should show the same dual-query fusion as iter_008/009, but with slightly reordered ranks when answer-type patterns match.
  - Prompt spans should show variable-length hit blocks (high-score hits longer, tail hits shorter) rather than uniform compression.
  - No "excerpts" or "focal" sections should appear in the prompt — the prompt remains a simple enumerated list of hits.
- Side effects to watch:
  - Proportional allocation may regress 1–3 previously-passing tasks if the score distribution is flat and the floor budget crowds out a critical sentence that a fixed wider window would have preserved.
  - Token consumption should stay roughly flat vs iter_009 (~1690 avg) because the total context budget is unchanged; completion tokens may drop slightly with the simpler prompt.

## Falsification
- If passrate does not improve or regresses, the answer-type boost is either too weak (15%) to reorder gold-bearing docs into the top hits, or the proportional allocation is fragmenting evidence across hits in a way that hurts synthesis.
- If empty predictions stay at ~10, the issue is not prompt verbosity but the 512-token generation ceiling or a deeper Qwen3 serving-layer bug, and the simpler prompt change was ineffective.
- If the unknown cluster stays flat while empty predictions drop, the remaining unknowns are genuine retrieval misses (gold docs outside the top-8 pool) that boosting cannot fix, confirming retrieval coverage is the dominant failure family.
