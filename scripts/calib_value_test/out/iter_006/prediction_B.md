# iter_006 prediction

## Candidate
contiguous_window_compression

## Mechanism
Replace iter_005's destructive list-block preservation with bounded contiguous relevance windows, re-apply iter_004's calibrated retrieval scaffold, use a synthesis-permissive prompt, and set a 512-token generation ceiling.

## Outcome prediction
- Train passrate Δ: [−0.03, +0.02] from iter_005's 0.39 baseline, staying flat at ~0.36–0.41. The mechanism does not recover iter_004's 0.49 level.
- Failure type movement:
  - "unknown/empty" cluster remains the dominant failure mode (~35–42 failures), failing to shrink as hoped
  - "wrong_answer" cluster stays roughly stable (~5–10 failures)
  - Empty predictions remain very low (2–4 tasks), indicating the 512-token budget and simpler prompt avoid Qwen3 hidden-thinking truncation
  - Several tasks that iter_004 passed remain regressed (~10–14 tasks)
- Trace movement:
  - Prompt tokens stay in the 1400–1600 range (bounded contiguous windows prevent the bloat that killed iter_005)
  - Completion tokens stay well under the 512 ceiling for most tasks
  - Fewer list-truncation artifacts than iter_005, but the grant-objectives task (8cf51dda) and cocktail task (3249768e) still fail because the contiguous window misses the exact list item or truncates the enumeration
- Side effects to watch:
  - Minimal risk of context budget exhaustion (per-hit max is strictly 5 sentences)
  - No significant change in token consumption vs iter_005
  - Synthesis-permissive prompt does not materially reduce abstention; the unknown cluster persists because retrieval quality (not compression or prompt) is the binding constraint for most failures

## Falsification
- Passrate above 0.45 would refute the prediction and indicate that re-applying iter_004's scaffold plus contiguous compression successfully recovered performance.
- The unknown cluster shrinking below 30 failures would indicate the synthesis-permissive prompt had meaningful leverage, which the evidence suggests it does not.
- Empty predictions spiking above 10 would indicate Qwen3 sensitivity to the prompt wording, contradicting the observed stability of simpler prompts in prior iterations.
