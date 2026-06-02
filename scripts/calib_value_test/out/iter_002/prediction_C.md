# iter_002 prediction

## Candidate
memgpt_calibrated_ranking

## Mechanism
Four coordinated changes:
1. **Score calibration & ranking**: removes fixed +0.2/+0.1 additive boosts from summary/core scores, normalizes RRF scores to [0,1], and reorders hits by raw score (tier becomes tiebreaker only). This lets relevant archival/recall passages compete for top context slots instead of being locked behind summary/core metadata.
2. **Generation budget**: increases `max_tokens` from 256 to 512 and falls back to `reasoning_content` when final `content` is empty. This directly targets the 25 tasks that produced empty predictions while burning exactly 256 tokens.
3. **Prompt simplification**: strips the "quote the relevant part" instruction in favor of concise direct answering, reducing token burn in the output.
4. **Retained compaction**: keeps iter_001's per-hit truncation (max_hit_chars=1200) and compact archival/recall formatting so more documents fit in the 6000-char budget.

## Outcome prediction
- **Train passrate Δ**: [+0.12, +0.20] (from 0.38 to ~0.50–0.58)
- **Failure type movement**:
  - The "empty prediction" cluster (25 tasks, all consuming 256 completion tokens) should shrink dramatically — 10–18 of these should convert to correct answers via the doubled token budget, reasoning_content fallback, and concise prompt.
  - The "truncated context / low-ranked evidence" cluster should shrink — 3–8 additional tasks should pass because relevant archival/recall docs now surface in the top-2 slots instead of being pushed out by boosted summary/core metadata.
  - The "unknown" cluster may shrink slightly (2–4 conversions) as better evidence ordering and a less conservative prompt help the model extract answers it previously rejected.
- **Trace movement**:
  - Completion tokens should rise from a median near 150–256 to ~200–400 for previously empty tasks.
  - Retrieved documents actually included in the prompt should increase from ~3–4 to ~5–7 because archival/recall docs now rank higher and max_hit_chars truncation prevents any single doc from monopolizing the budget.
  - Empty-string predictions should drop from 25 to <5.
- **Side effects to watch**:
  - Removing tier priority could cause 0–3 regressions among stable-pass tasks if they relied on summary/core ranking to keep a specific passage in-context, though summary/core are usually low-information metadata.
  - The reasoning_content fallback may produce verbose, unformatted text that the judge scores partially; watch for predictions that contain the correct answer buried in reasoning chains but lack the "FINAL ANSWER:" delimiter.
  - Token consumption per task will increase because max_tokens doubled; average completion tokens may rise by ~50–100.

## Falsification
- If passrate stays below 0.45, the mechanism is falsified: either the model still cannot extract answers even with more tokens and better ranking, or the reasoning_content fallback and prompt simplification do not translate to judge-scorable predictions.
- If empty predictions remain >15, the token-budget / reasoning_content fix did not work as hypothesized.
- If regressions exceed 5, removing tier priority is actively harmful despite the score normalization.
