# iter_014 prediction

## Candidate
list_atomic_compression_with_directive_prompt

## Mechanism
Two bounded changes atop the iter_013 multi-granularity retrieval scaffold:
1. **List-atomic compression**: In `build_answer_messages`, top-2 hits containing structured lists with 3+ items get a dynamic sentence budget of `list_items + 2` (instead of fixed 5) when the question matches list-related `_answer_type_patterns`. This preserves complete list blocks in context while keeping per-hit length bounded.
2. **Directive prompt tweak**: The system prompt shifts from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (to ~0.64–0.67)
- Failure type movement: Unknown/abstain failures should shrink by 2–4 tasks (the two canonical fixes—3249768e list truncation and 8aef76bc synthesis conservatism—plus 0–2 additional partial-evidence abstentions). Retrieval-miss unknowns (~14 tasks with genuinely no relevant info) should remain unchanged. Wrong-answer failures might rise by 0–1 if the prompt makes the model over-confident on partial evidence (e.g., 60036106 or 5025383b). Empty predictions should stay flat.
- Trace movement: Top-2 hits for list questions should show expanded sentence windows. Fewer traces should end with "FINAL ANSWER: unknown" when retrieved docs contain partial but directly relevant information.
- Side effects to watch: Prompt tokens stay roughly unchanged (same `max_context_chars`). Completion tokens may tick up slightly as the model produces substantive answers instead of "unknown." Risk of regression on the 6 true-negative tasks that passed with "unknown" in iter_013 is low because those contexts genuinely contain no relevant information at all, so the new wording still permits unknown.

## Falsification
- If passrate does not improve or regresses, the prompt wording is either too subtle to change model behavior or the increased willingness to guess converts partial-evidence unknowns into wrong answers at a higher rate than expected.
- If unknown failure count does not drop below 23, the prompt change is insufficient to overcome the model's abstention bias on partial evidence.
- If empty predictions rise above 4, the broader context or prompt length is somehow triggering output failures.
