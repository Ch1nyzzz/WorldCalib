# iter_012 prediction

## Candidate
answer_signal_prioritized_two_tier_context

## Mechanism
The candidate targets the dominant failure family from iter_011: Qwen3 hidden-thinking truncation causing empty predictions (10 tasks) and prompt-complexity-induced abstention (34 unknown/abstain). It replaces iter_011's list-skeleton + ** highlighting with:
1. **1024-token generation budget** — directly counters hidden-thinking truncation that produced empty outputs at the 512-token ceiling.
2. **Minimal prompt** — strips ** highlighting, list-preservation logic, and verbose instructions to avoid triggering Qwen3 reasoning mode.
3. **Answer-signal prioritization** — detects answer-type cues (number, date, list, yes/no) from the question and reorders retrieved hits so that hits containing matching cues appear first.
4. **Two-tier compression** — Tier-1 hits (top 2 or answer-signal hits) get minimal compression (up to 1000 chars) preserving the most promising evidence in full; Tier-2 hits get aggressive 3-sentence window compression to preserve context budget.

The retrieval foundation is explicitly preserved: dual-pass keyword retrieval, RRF normalization, score-first tier sorting, compact formatting, and reasoning_content fallback.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (from iter_011's 0.47 to ~0.50–0.54)
- Failure type movement: Empty predictions should drop from 10 to 3–5 (the 4 confirmed iter_010→iter_011 regressions — 60bf93ed, 85fa3a3f, gpt4_1916e0ea, gpt4_74aed68e — should recover, plus 1–2 additional empty fixes from the larger budget). Unknown/abstain should shrink by 2–4 tasks as Tier-1 minimal compression lets the model synthesize evidence that was previously truncated. Wrong-answer count should stay flat at ~9 or rise by at most 1.
- Trace movement: Empty-string predictions should decrease significantly; compressed hits should show fuller Tier-1 content (up to 1000 chars) and shorter Tier-2 snippets; no ** wrapping or list-skeleton artifacts in prompts.
- Side effects to watch: Token consumption will rise due to the 1024-token generation budget and larger Tier-1 hit budgets. Risk of regressions from aggressive 3-sentence Tier-2 truncation dropping disambiguating evidence, or from answer-signal misprioritization reordering truly relevant hits lower.

## Falsification
- If passrate does not improve or regresses, the 1024-token budget and minimal prompt did not fix Qwen3 hidden-thinking truncation, or the two-tier compression caused more regressions than the empty-prediction fixes it delivered.
- If empty predictions stay at ~10, the generation budget is not the binding constraint on Qwen3 output truncation, and the failure family is misdiagnosed.
- If unknown/abstain grows while empty drops, the minimal prompt is too permissive and the model is substituting empty outputs with conservative abstentions.
