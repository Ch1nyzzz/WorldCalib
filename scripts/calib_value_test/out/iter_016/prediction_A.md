# iter_016 prediction

## Candidate
sentence_surfacing_with_structure_preservation

## Mechanism
The dominant remaining failure families are (1) synthesis failures where evidence is present in retrieved hits but the model cannot extract it, and (2) list-truncation regressions where structured enumerations are compressed away. Two independent evidence sources support this:
1. Task 8aef76bc (sealant): the retrieved hit contains "Seal the vase with Mod Podge or another sealant," yet the model answers unknown — a clear synthesis failure.
2. Task 7405e8b1 (HelloFresh vs UberEats): UberEats discount evidence appears in multiple lower-ranked retrieved hits (indices 3, 4, 18, 19, 25, 27), yet the model says the context lacks UberEats discount info — evidence is present but not salient enough.
3. Task 3249768e (cocktail fifth bottle): a 5-item list is compressed to 4 items, cutting off the 5th bottle (Absinthe) — a structure-truncation failure.

The new mechanism restructures how each hit is presented to the model: (a) split each hit into sentences/list-units, (b) score each unit by query relevance, (c) re-order units so the most relevant ones appear first, and (d) preserve complete short lists (≤8 items) without reordering or truncation. This surfaces answer-bearing content front-and-center within each hit without adding any preamble, markdown formatting, or cross-hit complexity. It is general because any QA system benefits from having the most relevant evidence visible first, and short structured lists are ubiquitous in conversational memory.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (to ~0.69–0.73)
- Failure type movement: Unknown/abstain cluster should shrink by 3–5 tasks (synthesis failures where evidence was buried). Empty predictions might shrink by 1–2 tasks (better-structured context reduces hidden thinking). Wrong answers should stay flat or shrink by 1.
- Trace movement: For previously failed synthesis tasks, the answer-bearing sentence should now appear at the beginning of its hit. For list questions, the complete list should be visible in the top hits.
- Side effects to watch: Slightly longer average prompts if more list blocks are preserved. Risk of confusing temporal narrative if sentence reordering disrupts cause-effect flow within a turn — mitigated by only reordering within single-turn hits and preserving contiguous blocks when they form a temporal sequence.

## Falsification
- If passrate does not improve or regresses, sentence reordering within hits is either (a) destroying coherence the model needs, or (b) the unknown cluster is dominated by genuine retrieval misses rather than synthesis failures.
- If empty predictions increase, the longer prompts from preserved lists are triggering more hidden thinking in Qwen3.
- If wrong-answer count rises, front-loading relevant sentences is causing the model to overweight out-of-context snippets and hallucinate.
