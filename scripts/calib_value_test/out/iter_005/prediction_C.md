# iter_005 prediction

## Candidate
structure_preserving_adaptive_context

## Mechanism
Replace fixed 4-sentence per-hit compression with structure-aware adaptive context assembly: list-atomic compression (preserve entire list blocks when any item is query-relevant), dynamic relevance-weighted sentence budgets (3/5/8 sentences by confidence), archival list preservation, and a softer abstention prompt.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (from iter_004’s 0.49 baseline to ~0.52–0.56)
- Failure type movement:
  - "unknown" cluster shrinks by 3–6 (list-atomic fixes over-abstention on truncated lists; softer prompt reduces scattered-evidence abstentions)
  - "wrong_answer" cluster shrinks by 2–4 (8fb83627 and similar list-counting errors should recover when full lists are preserved)
  - "empty" cluster stable or shrinks by 0–1 (remaining empties are mostly hard generation-boundary issues not directly targeted)
- Trace movement:
  - Predictions for list-related queries will contain full enumerations instead of "unknown"
  - Completion tokens for high-confidence hits will be longer (up to 8 sentences vs flat 4)
  - Prompt context may include slightly fewer total hits because list preservation consumes more characters per hit
- Side effects to watch:
  - Prompt token count may rise 5–15% from preserved lists, potentially crowding out tail hits
  - Risk of extracting wrong list item if model picks wrong element from a preserved multi-item list
  - Softer abstention could increase hallucinated answers on genuine retrieval misses

## Falsification
- Passrate below 0.51 would refute the claim that list-atomic compression recovers the iter_004 regressions (8cf51dda, 8fb83627)
- "unknown" cluster shrinking by fewer than 2 would mean the softer abstention prompt has no measurable effect and list truncation was not a dominant abstention cause
- New regressions in non-list tasks would indicate context crowding from longer hits is outweighing the list-preservation benefit
