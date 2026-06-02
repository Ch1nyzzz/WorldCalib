# iter_020 prediction

## Candidate
multi_objective_compression_with_answer_type_scoring

## Mechanism
Restores the exact iter_016 proven stack (multi-signal retrieval, multi-granularity archival, adaptive limits, 1024-token budget, minimal prompt). Replaces single-objective sentence compression in `_compress_hit` with a multi-objective score (0.65 relevance cosine + 0.35 answer-type likelihood). Answer-type heuristics boost sentences containing numbers for quantitative questions, dates/time words for temporal questions, yes/no markers for binary questions, and list markers for enumeration questions. Compressed units are joined with newlines instead of spaces. The system prompt is also softened from "contains the answer" to "contains the answer or enough facts to infer it."

## Outcome prediction
- Train passrate Δ: [+0.00, +0.03] (to ~0.69–0.72)
- Failure type movement: The list-truncation cluster (8cf51dda) should convert from persistent fail to pass because list-marker boosting preserves all three objectives. The empty-prediction regression seen in iter_019 (0db4c65d) should revert to pass because the exact iter_016 stack is restored. A small number of quantitative persistent fails (e.g., 129d1232 total-money, 157a136e grandma-age) may flip if number boosting surfaces answer-bearing sentences that pure cosine buried. The broad "unknown" cluster (retrieval failures like 0edc2aef, 195a1a1b) should stay flat because compression cannot fix missing retrieval.
- Trace movement: For 8cf51dda, compressed context should now show all three numbered objectives instead of two. For quantitative and temporal tasks, traces should show more number/date-bearing sentences in the top compressed slots. Newline separators should be visible between compressed units. The inference prompt may produce slightly more inferential phrasing (e.g., "Based on X and Y, the answer is Z") on under-specified questions.
- Side effects to watch: The 0.35 weight on answer-type heuristics could occasionally boost an irrelevant sentence that happens to contain a number or date, displacing a more relevant prose sentence. The softened inference prompt could increase hallucinated answers on tasks where retrieval is poor. Token consumption should remain roughly flat (~180K).

## Falsification
- If passrate does not reach at least 0.68, the iter_016 stack restoration was incomplete or the answer-type scoring introduced regressions that overpower the gains.
- If the wrong-answer count rises by more than 2–3 tasks, the answer-type heuristics are producing false positives (irrelevant sentences with surface markers crowding out truly relevant ones).
- If empty predictions increase, there is a bug in the prompt or compression pipeline.
