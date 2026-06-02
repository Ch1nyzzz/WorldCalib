# iter_005 prediction

## Candidate
structure_preserving_adaptive_context

## Mechanism
Replace fixed 4-sentence per-hit compression with structure-aware adaptive context assembly.

1. **List-atomic compression**: Detect numbered/bullet lists within retrieved hits. When any list item is query-relevant, preserve the entire list block rather than compressing it to a fixed sentence count. This fixes regressions like 8cf51dda (grant objectives compressed away) and persistent failures like 3249768e (cocktail list truncated).

2. **Dynamic relevance-weighted sentence budgets**: Allocate sentences per hit proportionally to its relevance score instead of a flat 4-sentence cap. High-confidence hits (score > 0.95) get up to 8 sentences; medium-confidence hits get up to 5; low-confidence hits get up to 3. This preserves more signal from the hits most likely to contain the answer while still trimming noise from tail hits.

3. **Archival list preservation**: In memgpt_scaffold.py, make the 300-char turn truncation list-aware. If a turn contains a numbered or bulleted list, preserve the full list even if it exceeds the character limit. This recovers answers that live inside truncated list turns.

4. **Generation budget liberation**: Fix the hidden base.py max_tokens=256 hardcode to 512 (confirmed load-bearing from iter_004).

5. **Slightly softer abstention prompt**: Change "If the context does not contain the answer, say unknown" to "If the context is insufficient, answer unknown" to reduce over-abstention when evidence is present but scattered.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (from iter_004’s 0.49 baseline to ~0.53–0.59)
- Failure type movement:
  - "unknown/empty" cluster shrinks by 4–8 (structured answers now visible in context)
  - "wrong_answer" cluster stable or shrinks slightly (better evidence coverage)
  - Regressions from iter_002 eliminated (8cf51dda and similar list questions)
- Trace movement:
  - More predictions contain exact enumeration phrases ("1. To identify...", "5. Absinthe")
  - Completion tokens stable (512 budget already in use)
  - Prompt tokens may rise 5–15% on list-heavy tasks but stay within budget
- Side effects to watch:
  - Context budget exhaustion on queries with many long lists (mitigated by dynamic budgeting for low-relevance hits)
  - Risk of including irrelevant list items when a list is partially relevant

## Falsification
- Passrate below 0.50 would suggest list preservation adds noise or bloat that hurts more than it helps
- "unknown" cluster not shrinking would mean most failures are genuine retrieval misses, not compression artifacts
- Breakthroughs below 5 would indicate the mechanism lacks leverage on this split
