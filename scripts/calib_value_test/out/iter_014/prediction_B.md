# iter_014 prediction

## Candidate
list_atomic_compression_with_directive_prompt

## Mechanism
The candidate targets the synthesis failure family where evidence is present in retrieved hits but the model either abstains or extracts a truncated answer. It layers two bounded changes on top of the proven multi-granularity retrieval stack:

1. **List-atomic compression** (model.py): For top-2 hits containing 3+ list items, when the question asks for a list-related answer (detected by `_answer_type_patterns`), the per-hit compression budget expands from a fixed 5 sentences to `list_items + 2`. This preserves complete list blocks while still bounding per-hit length.
2. **Directive prompt tweak** (model.py): The system prompt shifts from "If the context does not contain enough information, answer unknown" to "Only answer unknown if the context contains no relevant information at all." This reduces unnecessary abstention when evidence is present but partial.

Both changes are tightly scoped: list expansion applies only to the first two hits with clear list structure, and the prompt change is a wording shift without added reasoning instructions, so it should not trigger Qwen3 hidden thinking.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.05] (to ~0.64–0.68)
- Failure type movement:
  - Unknown/abstain should shrink by 2–6 tasks. The two iter_013 regressions (3249768e list truncation, 8aef76bc abstention) are the clearest targets; the prompt change may convert a few additional abstentions where evidence is present but partial.
  - Empty predictions should stay at 2–4 (prompt is minimal, generation budget remains 1024).
  - Wrong answers should stay flat or rise by at most 1 (lower abstention threshold increases hallucination risk slightly, but wrong-answer count has been low).
- Trace movement:
  - Top hits for list queries should show expanded sentence counts (e.g., 7 instead of 5 for a 5-item list).
  - Model outputs should contain fewer "Unknown" responses when the gold string appears in retrieved docs.
  - 3249768e and 8aef76bc should move from regressed back to stable pass.
- Side effects to watch:
  - Prompt tokens may rise ~3–8% for list-heavy queries due to the expanded top-hit budget.
  - Risk of 1–2 regressions if the expanded list context crowds out other hits within the global context budget.

## Falsification
- If train passrate does not improve or regresses, the list-expansion budget is still insufficient to preserve the critical item (e.g., cosine-based sentence selection drops the low-similarity list item despite the larger window), or the prompt wording change is too subtle to shift Qwen3 abstention behavior.
- If empty predictions rise above 4, the prompt change unexpectedly triggers hidden reasoning/thinking tokens in Qwen3.
- If the unknown cluster shrinks by fewer than 2 tasks, the dominant failure family in this regime is genuine retrieval misses rather than synthesis conservatism, and the prompt/compression fix is too narrow to matter.
