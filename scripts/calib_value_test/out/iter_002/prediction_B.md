# iter_002 prediction

## Candidate
memgpt_calibrated_ranking

## Mechanism
Iter_001 achieved 0.38 passrate with compact context formatting, but two failure families remain dominant:
1. **Cross-tier score miscalibration**: summary gets a fixed 0.2 boost and core gets 0.1, while archival/recall RRF scores max out near 0.03. This forces summary/core metadata into the top-2 context slots, pushing answer-bearing archival/recall passages down or out of the 6000-char budget.
2. **Empty predictions**: 25 fails produced empty strings while consuming exactly 256 completion tokens, indicating the model burns its generation budget on hidden reasoning/thinking tokens or verbose quoting before reaching FINAL ANSWER.

The fix removes fixed additive boosts from summary/core, normalizes RRF to [0,1], increases max_tokens to 512, simplifies the prompt to direct concise answering without quoting, and keeps iter_001's compact formatting.

## Outcome prediction
- Train passrate Δ: [+0.08, +0.12] (from 0.38 to ~0.46–0.50)
- Failure type movement:
  - Empty-prediction cluster shrinks from ~25 to ~10–15 (512 tokens + simpler prompt partially fixes hidden-thinking truncation, but later iterations show 1024+ tokens are needed for full elimination)
  - Unknown/abstain cluster shrinks modestly as ranking calibration lets answer-bearing archival/recall docs compete for top context slots
  - Wrong-answer count stays flat or rises by 0–2 because the simpler prompt is slightly less conservative
- Trace movement:
  - Retrieved documents in the actual prompt should increase from ~2–3 to ~4–6 as relevant archival/recall hits rise in rank and fit into the context budget
  - Completion tokens should rise from a tight 256 cluster to a broader 300–450 distribution
  - Prompt tokens stay roughly flat because compact formatting is preserved
- Side effects to watch:
  - Removing summary/core boosts is safe for most tasks because those tiers are largely generic metadata, but a few tasks where core/summary genuinely contain the answer could regress
  - 512 tokens may still be insufficient for Qwen3 hidden thinking on a subset of tasks; if empty predictions stay above ~15, the generation budget needs to go higher

## Falsification
- If passrate stays below 0.42, the mechanism is falsified: either the model cannot extract answers even with better-ranked context, or Qwen3 hidden thinking consumes the full 512-token budget and the reasoning_content fallback is ineffective.
- If empty predictions do not shrink below ~18, the 512-token increase is insufficient and the empty-output failure family is driven by prompt-induced hidden thinking rather than raw generation budget.
- If wrong answers grow by more than 3 tasks, the simpler prompt is too permissive and the tradeoff between reducing abstention and increasing hallucination is negative.
