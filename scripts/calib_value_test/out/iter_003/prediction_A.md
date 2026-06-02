# iter_003 prediction

## Candidate
token_economical_direct_extraction

## Mechanism
Three coordinated changes that address the dominant failure families in iter_002:

1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, which silently neutralized iter_002's attempt to raise the limit. This hard cap caused 18 empty predictions (all hitting exactly 256 completion tokens) and capped every other task at ≤256 tokens. Raising it to 512 removes the artificial ceiling.

2. **Direct-answer prompt redesign**: The current prompt lets the model generate reasoning before "FINAL ANSWER:", wasting tokens and increasing truncation risk. Adding "Do not explain your reasoning" suppresses verbose preamble, leaving more budget for the actual answer.

3. **Equitable per-hit context packing**: The current builder includes full hits until the 6000-char budget is exhausted, so a single 1700-char hit can crowd out 2-3 other relevant docs. Dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`) ensures more hits are visible, increasing evidence diversity.

## Outcome prediction
- Train passrate Δ: [+0.06, +0.12] (from 0.47 to ~0.53–0.59)
- Failure type movement:
  - "empty" cluster shrinks from 18 to <5
  - "unknown" cluster shrinks from 29 to ~20–24 (sub-family where gold is present in context)
  - "wrong_answer" cluster stable or grows by ≤2
- Trace movement:
  - No completion_tokens ceiling at 256
  - Prompt context includes more hits (7–8 vs 4–5)
  - Predictions are shorter and more direct
- Side effects to watch:
  - Completion tokens rise for previously empty tasks
  - Prompt tokens may rise slightly from more included hits
  - Risk of wrong-answer regression if model becomes over-confident

## Falsification
- Passrate below 0.52 falsifies the mechanism (the 256-token ceiling was not the main driver of empty predictions, or evidence diversity doesn't improve synthesis).
- Empty predictions remaining ≥10 suggests Qwen3 generates hidden thinking tokens regardless of max_tokens.
- Stable-pass regressions >2 indicate the direct-answer prompt is too aggressive for multi-line answers.
