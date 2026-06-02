# iter_029 prediction

## Candidate
temporal_date_boost

## Mechanism
Restore the proven iter_027 stack (multi-signal retrieval, MMR diversity reranking, 2048-token generation budget, sentence compression, adjacent archival hit merging) and add temporal date-aware boosting: after multi-signal fusion and before MMR selection, docs whose dates match literal month names or 4-digit years in the query receive a small relevance boost (+0.10 for month, +0.05 for year).

## Outcome prediction
- Train passrate Δ: [+0.02, +0.03] from 0.68 to ~0.70–0.71
- Failure type movement: The three iter_028 regressions (ba61f0b9, c4ea545c, f8c5f88b) should flip back to passing because the source reverts to the proven iter_027 stack. No additional persistent-fail tasks should be resolved because temporal boosting is extremely narrow: only three queries contain literal month names (10d9b85a, 80ec1f4f_abs, 5809eb10), and 10d9b85a has no April-dated docs in its retrieval pool while the other two already pass.
- Trace movement: Traces for the three regression tasks should show the same retrieval patterns as iter_027 and completions should return to their iter_027 forms (detailed answer for c4ea545c, "6 women" for ba61f0b9, "From a sports store downtown" for f8c5f88b). Traces for month-containing queries may show score bumps on date-matching docs but no material reordering because either no docs match (10d9b85a) or all top docs match uniformly (5809eb10).
- Side effects to watch: Token consumption should stay flat relative to iter_027 (~1830 avg). No empty-output regression because the 2048-token budget and reasoning_content fallback are preserved. No new wrong-answer regressions expected because the boost only affects ranking for a tiny fraction of queries and does not inject answer information.

## Falsification
- Passrate stays at or below 0.69 (would refute the hypothesis that restoring the iter_027 stack reliably recovers the three known regressions).
- Any new task fails that passed in both iter_027 and iter_028 (would indicate an unanticipated side effect from temporal boost or from the tiny regex fix in model.py).
- Wrong-answer count rises by >1 (would indicate temporal boost is surfacing contradictory docs for the month-matched queries).
