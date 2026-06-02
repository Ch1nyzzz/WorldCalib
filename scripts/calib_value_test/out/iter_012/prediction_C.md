# iter_012 prediction

## Candidate
answer_signal_prioritized_two_tier_context

## Mechanism
The candidate addresses the iter_011 regression (passrate 0.47, down from 0.54 in iter_009) caused by prompt-complexity-induced abstention and Qwen3 hidden-thinking truncation. It replaces list-skeleton highlighting with: (1) max_tokens increased from 512 to 1024 plus a reasoning_content fallback to eliminate empty predictions; (2) answer-signal prioritization that reorders hits containing answer-type cues (numbers, dates, lists, yes/no) to the top; (3) two-tier compression where the top 2 hits get minimal compression (~1000 chars/5 sentences) and remaining hits get aggressive 3-sentence windowing; (4) a stripped-down direct-answer prompt.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (to ~0.50–0.54)
- Failure type movement: The empty-prediction cluster should shrink from 10 tasks to ~1–3 (direct effect of 1024 max_tokens + reasoning_content fallback). The unknown/abstain cluster should shrink from 39 to ~32–36 (minimal prompt reduces over-cautious abstention). The wrong-answer cluster may grow by 1–3 tasks as the model attempts more answers instead of defaulting to unknown.
- Trace movement: Top-2 hits should appear with longer text (up to 1000 chars), lower hits with 3-sentence windows. `**` highlighting and list-skeleton formatting should disappear. Answer-signal hits (e.g., number-containing passages for "how many" questions) should move to the front of the context.
- Side effects to watch: Token consumption should rise to ~175k–190k because of the doubled generation budget, partially offset by aggressive tier-2 compression. Risk of regressions on the two list tasks (`3249768e` gin bottles, `8cf51dda` endometrial cancer objectives) that passed in iter_011 due to list-skeleton preservation but may now see truncated lists under 3-sentence compression.

## Falsification
- If passrate does not reach at least 0.50: the loss of list-skeleton preservation plus aggressive 3-sentence tier-2 compression is hurting more than the empty-prediction and prompt-simplification fixes help.
- If empty predictions remain above 5: 1024 max_tokens is still insufficient for Qwen3 hidden-thinking output, or the reasoning_content fallback is not triggering correctly.
- If the unknown/abstain cluster grows rather than shrinks: the minimal prompt is paradoxically increasing abstention, possibly because the stripped instruction gives the model less confidence to commit to an answer.
