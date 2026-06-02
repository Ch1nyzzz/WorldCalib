# iter_004 prediction

## Candidate
query_focused_semantic_compression

## Mechanism
Iter_004 restores the retrieval-quality fixes that iter_002 proved were load-bearing (score-primary sorting, removal of arbitrary core/summary boosts, RRF normalization, compact core/archival/recall formatting) and layers on top of them the 512-token generation budget and direct-answer prompt from iter_003. The novel component is query-aware per-hit sentence compression: after retrieval, each hit is reduced to the 4 sentences most semantically similar to the query (cosine similarity over tokens), preserving metadata and original sentence order. This replaces the naive 1200-char truncation used in iter_002 and the equitable budget cap used in iter_003, aiming to increase evidence density so more distinct hits fit in the 6000-char context window while preserving answer-bearing content.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.10] (from iter_002's 0.47 to ~0.51–0.57)
  - Lower bound assumes semantic compression is roughly neutral versus iter_002's max_hit_chars=1200, so iter_004 mainly recovers iter_002's 47 passes plus the ~4 tasks that iter_003 uniquely fixed via 512 tokens/direct prompt (0.51).
  - Upper bound assumes sentence compression surfaces more relevant evidence per hit and fits 6–8 hits in context instead of 4–5, fixing an additional 3–6 persistent failures from iter_002 (0.54–0.57).
- Failure type movement:
  - "empty" cluster shrinks from ~18 to <8 (512-token budget + reasoning_content fallback removes truncation empties; 7 historically always-empty tasks may remain).
  - "unknown" cluster shrinks from ~29 to ~20–24 (retrieval ranking restored, so relevant archival/recall hits surface instead of being buried under low-scoring core/summary).
  - "wrong_answer" cluster stable or grows slightly from ~6 to ~7–10 (sentence compression risks dropping a critical sentence from a single long hit, causing 1–3 regressions).
- Trace movement:
  - top_hit_tier_distribution reverts to iter_002 pattern (archival ~70, recall ~30, core/summary near 0) instead of iter_003's core:100.
  - Prompt context includes 6–8 hits vs iter_002's 4–5 and iter_003's ~4.
  - Average prompt tokens drop slightly (~1500–1700) because compact formatting strips XML headers and verbose archival headers.
  - Average completion tokens rise toward ~1800 as the 512 ceiling is actually used for previously truncated tasks.
- Side effects to watch:
  - Risk of wrong-answer regression on tasks where the answer spans >4 sentences in a single hit (e.g., multi-objective or ordered-list questions).
  - Risk that reasoning_content fallback produces verbose non-answers for edge-case tasks where Qwen3 generates thinking tokens but no final content.
  - Token consumption higher than iter_002 due to 512 max_tokens, but lower than iter_003 because compact formatting reduces prompt size.

## Falsification
- Passrate below 0.50 would falsify the mechanism: it would mean either (a) semantic compression destroys more evidence than the naive 1200-char truncation, or (b) the direct-answer prompt + 512-token budget do not combine well with the restored retrieval, causing new synthesis failures.
- Empty predictions remaining ≥12 would suggest the 512-token ceiling and reasoning_content fallback are not the main drivers of empty predictions (contradicting iter_003's observed 12 empties).
- top_hit_tier_distribution still dominated by core/summary would mean the score-primary sorting change in memgpt_scaffold.py was not actually applied or is being overridden by the wrapper scaffold.
- Stable-pass regressions >3 would indicate that sentence compression is too aggressive for this model/judge combination, stripping critical supporting context on already-correct tasks.
