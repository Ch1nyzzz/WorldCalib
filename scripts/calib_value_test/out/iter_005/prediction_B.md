# iter_005 prediction

## Candidate
structure_preserving_adaptive_context

## Mechanism
Replace iter_004's fixed 4-sentence semantic compression with structure-aware adaptive context assembly, layered on the same calibrated retrieval stack (score-normalized RRF, compact formatting, 512-token generation budget).

1. **List-atomic compression**: Detect numbered/bullet lists within hits. When any list item is query-relevant, preserve the entire list block rather than compressing it to a fixed sentence count. This directly targets the two iter_004 regressions (3249768e cocktail list, 8cf51dda grant objectives) where answers were truncated away.

2. **Dynamic relevance-weighted budgets**: Allocate sentences per hit proportionally to its score (high >=0.95 gets up to 8, medium >=0.85 gets up to 5, low gets up to 3). This preserves more signal from top hits while trimming noise from tail hits.

3. **Archival list preservation**: Turn truncation in memgpt_scaffold.py becomes list-aware and the char limit rises from 300 to 500, recovering answers that live inside truncated list turns.

4. **Softer abstention prompt**: "If the context is insufficient, answer unknown" replaces the stricter "If the context does not contain the answer, say unknown", reducing over-abstention when evidence is present but scattered.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (from iter_004's 0.49 baseline to ~0.52–0.56)
- Failure type movement:
  - "unknown" cluster shrinks by 3–6 (the two list regressions convert, plus 1–4 additional synthesis failures where the softer prompt or preserved lists provide enough signal)
  - "empty" cluster stable or shrinks by 1–2 (512-token budget is already in place; no new budget change)
  - "wrong_answer" cluster stable (~7 tasks); the mechanism does not introduce new reasoning paths that would increase hallucination
- Trace movement:
  - Context blocks for top-scoring hits become longer when they contain lists (up to 8 sentences vs fixed 4)
  - Low-scoring tail hits become shorter (3 sentences vs fixed 4), slightly compressing noise
  - Predictions for list questions more often contain exact numbered/bulleted items from context
- Side effects to watch:
  - Prompt tokens may rise slightly because preserved list blocks are longer than 4-sentence summaries
  - Risk of 1–2 regressions if a preserved list block crowds out a different hit that contained the answer for an edge-case task
  - The 500-char archival limit (up from 300) increases average hit length; context budget pressure is the main countervailing force

## Falsification
- Passrate below 0.51 would mean the list-preservation heuristic fails to recover the known regressions or causes more damage via context crowding than it fixes.
- Passrate above 0.58 would imply the mechanism is unexpectedly effective at converting genuine retrieval misses, which is unlikely since retrieval ranking itself is unchanged from iter_004.
- 3249768e or 8cf51dda still failing would indicate the list-block detection or dynamic budget is not triggering correctly on the exact cases it was designed for.
- Empty predictions increasing would suggest the longer prompts from preserved lists are triggering Qwen3 hidden-thinking truncation, though the 512-token ceiling should contain this risk.
