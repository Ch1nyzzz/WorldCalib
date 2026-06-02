# iter_003 prediction

## Candidate
token_economical_direct_extraction

## Mechanism
Three coordinated changes that address the dominant failure families in iter_002:

1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, which silently neutralized iter_002's attempt to raise the limit. Raising it to 512 removes the artificial ceiling.

2. **Direct-answer prompt redesign**: Adding "Do not explain your reasoning" suppresses verbose preamble, leaving more budget for the actual answer.

3. **Equitable per-hit context packing**: Dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`) ensures more hits are visible, increasing evidence diversity.

## Outcome prediction
- Train passrate Δ: [+0.07, +0.15] (from 0.47 to ~0.54-0.62)
- Failure type movement:
  - Empty predictions should shrink dramatically (from ~18 to ~3-6)
  - 256-completion-token hits should disappear entirely
  - "unknown" predictions should shrink moderately (from ~29 to ~20-24)
  - Confident-but-wrong predictions may shrink slightly (from ~9 to ~6-8)
- Trace movement:
  - Completion tokens should no longer cluster at 256; distribution should shift leftward and downward as "Do not explain your reasoning" reduces preamble
  - Prompt tokens may stay flat or rise slightly from including more truncated hits
  - Retrieved context should show more distinct hit indices in prompts
- Side effects to watch:
  - Tasks where the answer sits at the end of a previously-included long doc may regress if truncation cuts it off
  - DeepSeek-v4-flash may ignore "Do not explain your reasoning" and still emit thinking tokens, in which case 512 tokens could still be tight for complex reasoning tasks
  - Including more hits could introduce noise on tasks where top-2 docs were already sufficient

## Falsification
If passrate stays below 0.53, the mechanism is falsified: either the 256-token empty predictions are caused by an API-level thinking-token behavior that max_tokens cannot fix, or equitable truncation is cutting off critical answer-bearing spans in long docs. If empty predictions remain above 10, the token-limit theory is wrong.
