# iter_006 prediction

## Candidate
contiguous_window_compression

## Mechanism
Replace iter_005's destructive list-block preservation with bounded contiguous relevance windows (max 5 sentences centered on peak query-similarity sentence), re-apply iter_004's calibrated retrieval scaffold (normalized RRF, no arbitrary boosts, compact formatting, 300-char archival truncation), and add a synthesis-permissive prompt that explicitly permits combining facts across passages and simple arithmetic.

## Outcome prediction
- Train passrate Δ: [+0.08, +0.15] (from iter_005's 0.39 baseline to ~0.47–0.54)
- Failure type movement:
  - "unknown" cluster shrinks by 8–14 (recovering the synthesis/abstention regressions introduced by iter_005's context bloat)
  - "wrong_answer" cluster stable or grows by 1–2 (synthesis prompt may occasionally misfire)
  - Empty cluster stable (~3 tasks)
- Trace movement:
  - More predictions contain arithmetic/combination phrases ("$120 + $20 = $140", "40% is higher than 20%")
  - Prompt tokens drop from iter_005's ~1,319 avg toward iter_004's ~1,409 avg or slightly below because per-hit length is tightly bounded
  - Fewer "unknown FINAL ANSWER: unknown" outputs
- Side effects to watch:
  - Risk of losing 1–2 iter_005 breakthroughs (e.g., 8cf51dda grant objectives) if a contiguous 4-sentence window truncates a long list that list-preservation previously kept whole
  - Risk of occasional wrong synthesis when the model combines unrelated numbers from different hits
  - Token consumption should decrease compared to iter_005 because full list blocks are no longer preserved

## Falsification
- Passrate below 0.45 would mean contiguous windows discard more relevant signal than iter_005's list-preservation added, or that the retrieval-scaffold revert failed to restore correct ranking
- "unknown" cluster shrinking by fewer than 5 would refute the core diagnosis that iter_005's failures were primarily abstention caused by context bloat
- Wrong-answer cluster growing by more than 3 would mean the synthesis-permissive prompt causes harmful hallucination on scattered-evidence tasks
