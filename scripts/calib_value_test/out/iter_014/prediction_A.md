# iter_014 prediction

## Candidate
list_atomic_compression_with_directive_prompt

## Mechanism
The dominant failure family from iter_013 is synthesis failures where evidence is present in retrieved hits but the model either abstains or extracts a truncated answer. Two independent evidence sources support this:
1. Task 3249768e (cocktail fifth bottle): the correct doc with Absinthe is retrieved and re-sorted to the top by answer-signal boosting, but sliding-scale sentence-window compression (5 sentences max) truncates the 5-item list to 4 items, cutting off Absinthe. The model explicitly says "only the first bottle (Sweet Vermouth) is mentioned."
2. Task 8aef76bc (sealant): "Mod Podge or another sealant" appears in a top-ranked recall doc, yet the model outputs "Unknown," indicating synthesis conservatism.

The new mechanism has two parts:
1. **List-atomic compression**: In `build_answer_messages`, when a top hit (idx ≤ 2) contains a structured list with 3+ items and the question asks for a list-related answer (detected by existing `_answer_type_patterns`), the compression budget is expanded to `list_items + 2` sentences instead of the fixed 5. This preserves the complete list block while still bounding per-hit length.
2. **Directive prompt tweak**: The system prompt is changed from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

Both changes are bounded: list expansion applies only to top-2 hits with clear list structure, and the prompt change is a wording shift, not a reasoning chain addition, so it should not trigger Qwen3 hidden thinking.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.07] (to ~0.66–0.70)
- Failure type movement: Unknown/abstain cluster should shrink by 3–5 tasks (list truncation fixes + reduced conservatism). Wrong answers might rise by 0–1 due to the more directive prompt. Empty predictions should stay at 0–3.
- Trace movement: For previously failed list questions, the full list block should now appear in the compressed prompt instead of a truncated window. For sealant-type tasks, predictions should shift from "unknown" to the extracted phrase.
- Side effects to watch: Prompt tokens may rise ~5% due to longer list blocks in top hits, but avg prompt tokens in iter_013 was 1639 with headroom. Risk of regression on tasks where a long list crowds out other hits is low because list expansion is capped at top-2 hits.

## Falsification
- If passrate does not improve or regresses, either the prompt wording triggers more hidden thinking / wrong answers, or the list-preservation crowds out critical evidence from other hits.
- If the unknown cluster does not shrink by at least 2 tasks, the synthesis failures are driven by something other than list truncation and prompt conservatism (e.g., vocabulary mismatch between query and evidence).
- If empty predictions rise above 5, the prompt change re-introduced Qwen3 hidden-thinking truncation.
