# iter_001 prediction

## Candidate
memgpt_source_compact_context

## Mechanism
The baseline suffers from two related failure modes:
1. Context truncation: archival passages average ~4800 characters, so with max_context_chars=6000 only 1-2 passages fit after core/summary, dropping most recall messages and lower-ranked archival hits.
2. Conservative generation: the model frequently outputs "unknown" even when the answer is present in the first few retrieved documents.

The fix compresses retrieved hits (more compact archival/recall formatting, per-hit truncation in context packing) and strengthens the answer prompt to explicitly instruct the model to search all passages before answering unknown.

## Outcome prediction
- Train passrate Δ: [+0.08, +0.18] (from 0.16 to ~0.24-0.34)
- Failure type movement: generation failures where gold is in early docs should shrink; truncation failures where gold is in later docs should also shrink
- Trace movement: prompt_tokens should stay roughly similar (shorter hits but more included); retrieved documents in the actual prompt should increase from ~2-3 to ~5-7
- Side effects to watch: truncation might cut off answers that appear at the end of long passages; if so we should see new failures where the answer was previously in-context but now truncated

## Falsification
If passrate stays below 0.20, the mechanism is falsified: either the model cannot extract answers even with better prompts, or the truncation strategy is removing critical evidence.
