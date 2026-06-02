# iter_012 prediction

## Candidate
answer_signal_prioritized_two_tier_context

## Mechanism
The dominant failure family is Qwen3 hidden-thinking truncation causing empty predictions (~10 tasks in iter_011) and prompt-complexity-induced abstention. The iter_011 list-skeleton + ** highlighting mechanism made both worse by increasing prompt complexity and trigger tokens.

The new mechanism is a two-tier context packing strategy paired with a larger generation budget:
1. **Increase max_tokens to 1024** to give Qwen3 room to finish hidden thinking and still emit an answer.
2. **Answer-signal prioritization**: detect answer-type cues (number, date, list, yes/no) from the question; reorder retrieved hits so that hits containing matching cues appear first.
3. **Two-tier compression**: Tier-1 hits (top 2, or all answer-signal hits if fewer) get minimal compression (up to 1000 chars) so the model can read the most promising evidence in full. Tier-2 hits get aggressive 3-sentence window compression to preserve context budget.
4. **Minimal prompt**: strip all formatting triggers (** highlighting, list-preservation logic, verbose instructions) and use the simplest direct-answer instruction.

The retrieval foundation is kept load-bearing: dual-pass keyword retrieval, RRF score normalization, score-first tier sorting, compact core/hit formatting, 300-char archival truncation, and reasoning_content fallback.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.12] (to ~0.52–0.59)
- Failure type movement: Empty predictions should shrink from 10 to 2–4 (1024-token budget + simple prompt). Unknown/abstain should shrink by 3–6 tasks (top hits are less compressed, making evidence easier to spot). Wrong-answer count should stay flat or rise by 1.
- Trace movement: Compressed hits should no longer contain ** wrapping or list-skeleton artifacts. Top hits should be longer and more readable. Completion tokens should show a bimodal distribution: short (~50–150) for easy tasks, long (~500–800) for tasks where hidden thinking occurs but now has room to complete.
- Side effects to watch: Token consumption will rise because of 1024-token completions on some tasks and larger top-hit context. Risk of regressions on tasks where the answer is in a tier-2 hit that gets aggressively truncated by the 3-sentence window.

## Falsification
- If empty predictions do not shrink below 5, the 1024-token budget is insufficient or the prompt still triggers hidden thinking; a more aggressive prompt simplification or temperature change would be needed.
- If passrate does not improve or regresses, the two-tier truncation may be dropping critical evidence in tier-2 hits, or the answer-signal detection may be too noisy and demote the true gold hit.
- If the unknown cluster stays flat while empty predictions improve, the remaining unknowns are genuine retrieval misses and context packing cannot compensate.
