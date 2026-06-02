# iter_010 prediction

## Candidate
answer_type_boosted_retrieval_with_proportional_context

## Mechanism
The dominant failure families are: (1) empty predictions caused by Qwen3 hidden thinking triggered by complex prompts, and (2) retrieval misses / synthesis failures where gold evidence is either not ranked highly enough or gets truncated by fixed per-hit compression.

The new mechanism layers two retrieval-side and context-packing changes on top of proven dual-pass retrieval and simplified formatting:

1. **Answer-type-aware retrieval boosting**: After dual-pass retrieval, detect the expected answer type from the question (numbers, dates, percentages, lists) using lightweight regex heuristics. Boost the scores of retrieved hits that contain matching patterns by 15%. This is general — any retrieval-based QA system benefits from ranking answer-bearing documents higher.

2. **Score-proportional context allocation**: Instead of compressing every hit to a fixed window or showing them at full length, allocate the global `max_context_chars` budget proportionally to each hit's relevance score. Each hit receives a minimum floor (200 chars), and the remainder is distributed by score share. Within each budget, a contiguous window around the most query-relevant sentence is preserved. This ensures high-confidence evidence is preserved in full while low-scoring hits are abbreviated, maximizing the chance the model sees the critical evidence.

The prompt is kept concise and direct (iter_006 style, without cross-hit excerpts) to avoid triggering hidden thinking. The 512-token generation budget is retained.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (to ~0.58–0.64)
- Failure type movement: The empty-prediction cluster should shrink from 8 to 3–4 (simple prompt reduces hidden thinking). The unknown cluster should shrink by 4–8 tasks (answer-type boosting surfaces gold evidence higher, and proportional allocation preserves it better). Wrong-answer count should stay flat or rise slightly.
- Trace movement: Retrieval docs should show re-ordered rankings where answer-bearing docs move up. Prompt context should show variable-length hits — high-scoring docs are longer, low-scoring docs are shorter.
- Side effects to watch: Token consumption should drop slightly because low-scoring hits are more aggressively truncated. Risk of regressions on tasks requiring synthesis across many low-scoring hits (but minimum floor preserves them).

## Falsification
- If passrate does not improve or regresses, the answer-type patterns may be too noisy or the proportional allocation may be crowding out cross-hit synthesis.
- If empty predictions stay at ~8, the issue is not prompt complexity but a deeper serving-layer bug, and the simpler prompt was ineffective.
- If the unknown cluster stays flat while empty predictions drop, the remaining unknowns are genuine retrieval misses and boosting cannot compensate.
