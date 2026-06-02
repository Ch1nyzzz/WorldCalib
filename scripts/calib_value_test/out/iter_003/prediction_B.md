# iter_003 prediction

## Candidate
token_economical_direct_extraction

## Mechanism
Three coordinated changes on top of the clean snapshot:
1. **Completion-budget liberation**: base.py hardcodes `max_tokens=256`, silently overriding model.py's 512 default. Raising base.py to 512 removes the artificial ceiling that caused 18 empty predictions in iter_002 (all hitting exactly 256 completion tokens).
2. **Direct-answer prompt redesign**: Adds "Do not explain your reasoning" to suppress verbose preamble and hidden thinking tokens, leaving more of the 512-token budget for the actual answer.
3. **Equitable per-hit context packing**: Replaces the "include full hits until budget exhausted" strategy with dynamic per-hit truncation (`max_hit_chars = max(700, 6000 // min(len(hits), 8))`), ensuring 6–8 hits are visible rather than 2–3 long hits crowding out the rest.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.16] (from iter_002's 0.47 to ~0.57–0.63)
- Failure type movement:
  - Empty predictions: should shrink from 18 to 4–7. The 512-token ceiling plus the reasoning suppression should convert the majority of truncation failures into completed outputs.
  - Unknown/abstain cluster: should shrink modestly from 23 wrong unknowns to ~19–21, as equitable packing surfaces additional relevant docs that were previously dropped from the 6000-char context window.
  - Wrong-answer count: should stay flat at ~6 or rise by at most 1–2, because hit truncation can cut off list items or late-sentence answers in long documents.
- Trace movement:
  - Completion tokens should become bimodal: most tasks still use <200 tokens, but the previously-empty cluster should now show 300–450 tokens.
  - Prompt tokens should stay similar (~1500–1700) because total context budget is unchanged; the difference is that budget is spread across more hits.
  - Retrieved context should show 6–8 hits included instead of the 3–5 typical in iter_002.
- Side effects to watch:
  - If Qwen3 generates hidden thinking tokens regardless of the prompt directive, some tasks may still burn the 512-token budget and return empty or truncated outputs.
  - Dynamic truncation of long hits could regress list-type answers (e.g., enumerations) if the answer-bearing item falls beyond the truncation boundary.
  - The `reasoning_content` fallback added in iter_002 may interact unpredictably with the new prompt; if the model emits reasoning into `reasoning_content` and nothing into `content`, the fallback could surface reasoning text instead of the answer.

## Falsification
- If passrate stays below 0.53, the mechanism is falsified: either the 512-token budget is insufficient to overcome Qwen3 hidden-thinking truncation, or equitable packing causes more regressions than the empty-prediction fixes deliver.
- If empty predictions do not drop below 10, the "Do not explain your reasoning" directive is ineffective at suppressing hidden token consumption, and the true bottleneck is model-level reasoning that a larger token budget alone cannot fix.
- If the unknown cluster does not shrink at all (or grows), the context-packing trade-off is net-negative: the loss of full-hit context for top-ranked documents outweighs the gain from including tail hits.
