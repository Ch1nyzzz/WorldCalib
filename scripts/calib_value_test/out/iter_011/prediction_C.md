# iter_011 prediction

## Candidate
fixed_window_list_skeleton_highlighting

## Mechanism
The candidate combines three proven elements from earlier iterations—fixed 5-sentence contiguous window (iter_006), peak-sentence highlighting (iter_008), and a simplified direct prompt (iter_006)—and adds a new structure-aware list-skeleton compression function. When a retrieved hit contains a numbered/bulleted/labeled list, the compressor preserves every list item as a heading/first-sentence stub instead of dropping whole items or cutting mid-description. This directly targets the list-truncation-induced abstention family observed in `3249768e` (cocktail bottles — passed only in iter_006, regressed in 008-010) and `8cf51dda` (endometrial cancer objectives — passed in 006/008, regressed in 009/010). The simplified prompt should also reduce empty-prediction failures caused by Qwen3 hidden-thinking (6 empty preds in iter_010 vs 3 in iter_006).

## Outcome prediction
- Train passrate Δ: [+0.01, +0.04] (from 0.53 to ~0.54–0.57)
- Failure type movement: list-truncation abstentions shrink by 2–3 tasks (`3249768e`, `8cf51dda`, and possibly `gpt4_31ff4165` or `gpt4_2f8be40d` if they were partial-list truncation). The empty-prediction cluster should shrink by 2–3 tasks (iter_006-style prompt). Wrong-answer count stays roughly flat.
- Trace movement: Prompt context for list-bearing hits should show complete list skeletons (e.g., all 5 bottles with first-sentence stubs, all 3 objectives with headings) rather than truncated mid-list snippets. Completion traces should show fewer blank outputs and fewer "only the first ... is visible" abstentions.
- Side effects to watch: Token consumption should rise from iter_010's ~154k toward iter_006's ~162k (list skeletons can be longer than aggressive proportional truncation). Risk of 1–2 regressions if list-detection heuristics misfire on non-list content and over-compress prose that needs full detail.

## Falsification
- If passrate does not improve or regresses, the list-skeleton logic either misfires on non-list content causing more harm than good, or the prompt simplification loses needed guidance.
- If `3249768e` and `8cf51dda` still fail, the list-skeleton mechanism is not actually surfacing the complete lists within the per-hit budget.
- If empty predictions stay at ~6, the prompt simplification was ineffective at suppressing Qwen3 hidden-thinking empty outputs.
- If token consumption drops instead of rising, the list skeletons are being aggressively truncated more than the proportional windows they replace.
