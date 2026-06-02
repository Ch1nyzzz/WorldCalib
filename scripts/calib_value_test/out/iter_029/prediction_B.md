# iter_029 prediction

## Candidate
temporal_date_boost

## Mechanism
Restore the proven iter_027 stack (multi-signal retrieval, MMR diversity reranking, 2048-token generation budget, sentence compression, adjacent archival hit merging) and add temporal date-aware boosting: after multi-signal fusion and before MMR selection, docs whose dates match explicit month names (+0.10) or years (+0.05) in the query receive a small relevance boost.

## Outcome prediction
- Train passrate Δ: [+0.00, +0.02] from the iter_027 baseline of ~0.71, yielding an absolute passrate of ~0.71–0.73 (equivalently, +0.03 to +0.05 from iter_028's 0.68).
- Failure type movement: The persistent-fail count should stay flat or drop by at most 1 task. The dominant unknown/abstain cluster (~29 tasks) will not shrink meaningfully because temporal boosting only handles explicit month/year queries, and the primary target (10d9b85a "April") likely has no April-dated docs in the corpus — the April workshop evidence is embedded inside May-dated conversation turns, which doc-date boosting cannot surface. The wrong-answer cluster (~15 tasks) and empty-output cluster (0 tasks) should remain unchanged.
- Trace movement: Retrieval spans for queries containing month names (e.g., "April", "May") or 4-digit years should show slightly elevated scores for docs with matching dates. No new breakthrough patterns or aggregation-language changes should appear in model completions.
- Side effects to watch: Token consumption should remain comparable to iter_027 (~1830 avg). No new empty-output regressions expected because the prompt/model tier is unchanged. The small boost magnitude (+0.10) limits the risk of surfacing noisy or contradictory docs.

## Falsification
- Passrate drops below 0.70 (would indicate the iter_027 stack restoration is imperfect or the temporal boost introduces unexpected regressions).
- Passrate exceeds 0.73 (would mean temporal boosting is fixing more tasks than the narrow signal can plausibly reach).
- Wrong-answer count rises by >2 (would indicate the boost is promoting contradictory or semantically mismatched but temporally aligned docs).
- Empty outputs reappear (would indicate a hidden prompt or model-tier change not documented in the diff).
