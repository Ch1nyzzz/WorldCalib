# iter_004 prediction

## Candidate
query_focused_semantic_compression

## Mechanism
Three coordinated changes on top of a clean source snapshot:

1. **Retrieval score calibration restoration**: Re-applies iter_002's load-bearing scaffold improvements that iter_003 lost—removing arbitrary score boosts (+0.1 core, +0.2 summary), normalizing RRF scores to [0,1], compacting archival/recall formatting, and sorting purely by relevance score. This should recover iter_002's ~0.47 passrate from iter_003's 0.27.

2. **Query-aware per-hit sentence compression**: After retrieval, each hit is compressed to at most 4 sentences ranked by cosine similarity to the query, preserving the first line as metadata. This increases evidence density in the 6000-char budget, allowing more distinct hits to reach the model.

3. **Generation budget and prompt fixes**: Fixes the hidden base.py max_tokens=256 hardcode to 512, adds reasoning_content fallback for Qwen3 hidden thinking, and uses a concise direct-answer prompt ("Do not explain your reasoning").

## Outcome prediction
- Train passrate Δ: [+0.22, +0.26] (from iter_003's 0.27 to ~0.49–0.53). Restoring iter_002's retrieval fixes the 6 regressions and recovers the 0.47 baseline. The 512-token budget and reasoning_content fallback should convert 3–5 of iter_002's 14 empty predictions to passes. Query compression adds a modest +2–4 breakthroughs from persistent fails by fitting more hits in context, while risking 1–3 regressions from destroyed list structure or dropped context.
- Failure type movement:
  - "empty" cluster shrinks from 12 (iter_003) / 14 (iter_002) to 4–6
  - "unknown" cluster stable or shrinks slightly (30 in iter_002 → 26–30)
  - "wrong_answer" cluster stable or grows by ≤2 (4 in iter_002 → 4–6)
- Trace movement:
  - Retrieval scores return to calibrated [0.9–1.0] range for top hits
  - Prompt context includes 6–8 compressed hits vs 4–5 full hits
  - Completion tokens no longer cluster at 256; empty predictions drop
  - Predictions are shorter and more direct due to concise prompt
- Side effects to watch:
  - List-structure questions (e.g., cocktail fifth bottle, grant objectives) may still fail or worsen because space-joined sentence compression destroys list formatting
  - Prompt tokens may rise slightly from more included hits
  - Risk of wrong-answer regression if compression drops disambiguating context from multi-sentence evidence

## Falsification
- Passrate below 0.48 would indicate the query compression is actively harmful or the retrieval restoration is incomplete/mismatched vs iter_002.
- Empty predictions remaining ≥8 would falsify the hypothesis that the 256-token ceiling was the main driver of empty outputs.
- More than 4 regressions from iter_002's pass set would indicate sentence-level compression with space joining is too destructive for this model and task distribution.
