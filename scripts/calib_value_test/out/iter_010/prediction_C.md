# iter_010 prediction

## Candidate
answer_type_boosted_retrieval_with_proportional_context

## Mechanism
The candidate removes cross-hit evidence distillation (iter_009) and returns to the concise iter_006-style prompt while keeping dual-pass retrieval from iter_008. It adds two retrieval-side changes:
1. Answer-type-aware boosting (15% score boost for hits containing number/date/percentage/list patterns matching the question type)
2. Score-proportional context allocation (distributing max_context_chars by relevance score share with a 200-char floor, preserving a contiguous window around the most query-relevant sentence per hit)

## Outcome prediction
- Train passrate Δ: [+0.01, +0.05] (to ~0.55–0.59)
- Failure type movement: The "unknown despite relevant docs" cluster should shrink modestly (by 2–4 items) as answer-type boosting pushes evidence-bearing passages higher. The empty-prediction cluster should stay flat or shrink slightly because the concise prompt avoids hidden-thinking triggers. Pure retrieval-miss failures (e.g., Miami hotel, April workshops) will remain unchanged.
- Trace movement: Spans should show variable-length hits proportional to scores instead of uniformly compressed hits. No "Relevant excerpts" section at the top of prompts (that was iter_009). Completion tokens should stay in the 60–350 range; no spike in 512-token completions.
- Side effects to watch: Token consumption may drop slightly due to more efficient budget allocation, or shift higher for tasks where a single high-score doc dominates. Risk of regression on list/objective questions if the 200-char floor is too small for low-scoring but necessary supporting docs.

## Falsification
- If passrate stays flat or drops, the 15% boost is too weak to reorder meaningful ranks, or proportional allocation loses more signal from low-scoring docs than it gains from high-scoring ones, and the removal of cross-hit distillation is not compensated.
- If empty predictions rise above the iter_009 level (~3–5 tasks), the prompt or context-packing change is somehow more prone to triggering Qwen3 hidden thinking despite being concise.
- If the "unknown despite relevant docs" cluster does not shrink, the regex-based answer-type detection is not actually surfacing the answer-bearing passages, indicating the failure is synthesis-level rather than ranking-level.
