# iter_016 prediction

## Candidate
sentence_surfacing_with_structure_preservation

## Mechanism
The change replaces peak-centered sentence-window compression with per-hit global relevance sorting: each hit is split into sentences/list-units, units are scored by query-token cosine similarity, and the top-N most relevant units are surfaced first within the hit. Complete short structured lists (≤8 items, ≥50% list markers) are preserved intact without truncation or reordering. Numbered list items (e.g., "1. Sweet Vermouth") are now correctly detected as atomic units, fixing a bug in the prior sentence splitter.

This targets the dominant residual failure family where evidence is present in retrieved hits but the model either cannot find it (synthesis failure) or the evidence is in a structured list that gets truncated by coarse compression. Two independent evidence sources support this:
1. Task 3249768e (cocktail fifth bottle): iter_014–015 list-atomic compression still truncated the 5-item list to ~4 items; the model explicitly says "only the first bottle (Sweet Vermouth) is mentioned."
2. Task 8aef76bc (sealant): the top-2 recall hit contains "Seal the vase with Mod Podge or another sealant," yet the model outputs unknown — the sentence is buried in a long hit and missed by peak-window compression.
3. Task 7405e8b1 (HelloFresh vs UberEats): UberEats discount evidence appears in retrieved hits 3–4 but the model says it is missing, indicating salience failure within compressed hits.

The mechanism should transfer because any retrieval-then-synthesis pipeline over long documents risks (a) truncating structured lists and (b) burying answer-bearing sentences inside long passages. Surfacing the most relevant units first is a general information-flow improvement.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.05] (to ~0.68–0.71)
- Failure type movement:
  - List-truncation cluster shrinks by 1–2 tasks (3249768e likely fixed; 8cf51dda may recover if its numbered objectives are now preserved as a short list).
  - Synthesis/abstention cluster shrinks by 1–2 tasks (8aef76bc and 7405e8b1 should see answer-bearing sentences moved to the front of their hits).
  - Empty-prediction cluster (8cf51dda, 982b5123, gpt4_21adecb5) is likely stable: these tasks showed empty predictions with 1024 completion tokens in iter_014–015, suggesting a model-level max_tokens/reasoning loop issue rather than a context-salience issue.
  - Wrong-answer cluster: stable.
- Trace movement:
  - For 3249768e, compressed top hits should now contain all five bottles as a preserved list block instead of a truncated subset.
  - For 8aef76bc, the sealant sentence should appear in the first 1–3 units of the compressed DIY hit.
  - For 7405e8b1, UberEats discount sentences should rank highly within hits 3–4 and appear at the front of those blocks.
- Side effects to watch:
  - Prompt tokens may rise slightly for hits containing short lists (preserved completely instead of truncated).
  - Regression risk on tasks that depend on chronological or causal coherence within a single long hit, because global relevance sorting reorders sentences and breaks narrative flow. Likely low (only long hits are reordered, and short lists are exempt), but non-zero.

## Falsification
- If passrate does not improve or regresses, either (a) sentence reordering breaks coherence in more tasks than it helps, or (b) the recoverable failures are driven by retrieval misses or model-level generation issues that context reorganization cannot fix.
- If 3249768e remains failed, short list preservation is insufficient — the 5-bottle list may be split across multiple hits or missed by the list detector.
- If 8aef76bc remains failed, the synthesis failure is not due to evidence salience but to a deeper model bias or reasoning behavior.
- If the empty-prediction tasks (8cf51dda, 982b5123, gpt4_21adecb5) remain empty with 1024 completion tokens, the failure family is model-level max-token exhaustion, not context packing.
