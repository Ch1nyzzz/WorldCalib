# iter_001 prediction
## Candidate
memgpt_source_compact_context

## Mechanism
Compress retrieved hits through compact archival/recall formatting, per-hit truncation (max_hit_chars=1200), shorter per-turn archival building (300 chars), and a simplified core-memory representation. Strengthen the answer prompt to explicitly instruct the model to read all passages before answering unknown. Additionally, sort deduplicated hits by score first rather than tier first, so higher-scoring evidence is retained in the limited context window.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.18] to ~0.26–0.34
- Failure type movement: The dominant "unknown/abstain" cluster should shrink significantly (from ~81 to ~50–60 tasks) as more evidence becomes visible and the prompt reduces conservative abstention. The retrieval-miss cluster stays roughly flat at ~40 tasks. Wrong answers should increase modestly from ~2 to ~5–10 as the model answers more aggressively.
- Trace movement: Context spans should show 5–7 hits in the prompt instead of the baseline 2–3. Predictions should contain fewer verbatim "unknown" outputs and more direct answers.
- Side effects to watch: Completion-token counts may rise slightly due to longer reasoning before FINAL ANSWER, but empty/truncated outputs should remain rare (<5 tasks) because the prompt is only moderately more verbose. A small number of tasks may regress if score-first sorting demotes a previously load-bearing core/summary hit, though core memory rarely contains specific answers.

## Falsification
- If train passrate Δ is below +0.05, the mechanism failed: either compression did not bring gold-bearing docs into the visible context, or the prompt change did not reduce abstention.
- If empty predictions spike above 10, the prompt is triggering Qwen3 hidden-thinking truncation despite its moderate length.
- If wrong answers grow above 15, the directive prompt is too permissive and causing hallucinations.
- If the passrate regresses vs baseline (0.16), the tier-sort-key change or per-turn archival truncation is actively destroying answer-bearing evidence.
