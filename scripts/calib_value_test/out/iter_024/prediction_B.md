# iter_024 prediction

## Candidate
dynamic_contiguous_compression_top8

## Mechanism
Restore the iter_020 stack (0.69 passrate) and layer two runtime changes in `model.py` plus a generation-budget increase in `base.py`:
1. Dynamic relevance-proportional sentence allocation replaces fixed tiered compression (5/3/2). Each hit gets `max(2, min(7, round(2 + 5 * hit.score/max_score)))`, giving the strongest hits up to 7 sentences.
2. Contiguous-window compression replaces globally sorted top-k sentence selection. The highest-scoring sentence in a hit is located, and a contiguous window around it is preserved, keeping list order and local context intact.
3. Generation budget raised from 1024 to 1536 tokens.

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from 0.69 to ~0.70–0.73)
- Failure type movement:
  - Empty-output cluster shrinks from 4 to 0–2. Diagnostic evidence: all 4 iter_020 empty tasks emitted exactly 1024 completion tokens, confirming max_tokens truncation. Historical traces show 2 of these tasks (gpt4_21adecb5, 4f54b7c9) passed under prior iterations when not truncated; gpt4_7abb270c consistently fails; 0bc8ad93 consistently outputs a wrong answer ("yes/with a friend") when given budget. Thus ~2 of the 4 empties should convert to passes.
  - Unknown/abstain cluster shrinks by 1–3 tasks. The contiguous window preserves list order and local context in top hits, and the dynamic allocation gives the top 1–2 hits up to 7 sentences (vs 5), which should surface enough context for a few synthesis failures where evidence was present but scattered or truncated.
  - Wrong-answer cluster stays roughly flat (7±1). 0bc8ad93 may convert from empty to wrong, offsetting any wrong→pass improvements elsewhere.
- Trace movement:
  - Fewer predictions with exactly 1024 completion tokens.
  - More top-hit blocks showing contiguous sentence sequences (especially numbered/bulleted lists) rather than globally reordered sentences.
- Side effects to watch:
  - Average prompt token count may rise slightly because top hits can now expand to 7 sentences.
  - Risk of 0–2 regressions on tasks where the answer depends on two widely separated passages within a single long document; the contiguous window cannot cherry-pick both regions, whereas iter_020's global sort could.

## Falsification
- If train passrate does not improve by at least +0.01, then either (a) the 1536-token ceiling does not resolve the empty-output truncation, (b) contiguous-window compression is missing scattered evidence in top hits and causing regressions that cancel the empty-output gains, or (c) the dynamic allocation is adding noisy low-scoring sentences to high-scoring hits.
- If the wrong-answer count rises by more than 2, contiguous window is destroying cross-region evidence in long documents.
- If empty outputs do not shrink despite 1536 tokens, Qwen3 hidden-thinking behavior is not governed by the explicit generation budget.
