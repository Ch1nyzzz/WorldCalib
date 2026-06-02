# iter_008 prediction

## Candidate
keyword_augmented_dual_pass_retrieval

## Mechanism
The candidate adds stopword-stripped dual-pass hybrid retrieval (BM25+cosine) fused with RRF for both archival and recall tiers, highlights the peak-relevance sentence in each compressed hit with `** **`, and softens the system prompt to explicitly permit synthesis and only abstain when no relevant information exists.

## Outcome prediction
- Train passrate Δ: [+0.08, +0.18] (from 0.50 baseline to ~0.58–0.68)
- Failure type movement:
  - Retrieval-miss abstentions should shrink: fewer "unknown" answers where the gold document was missed because stopwords diluted the query embedding.
  - False-abstention cluster should shrink: tasks where relevant docs were retrieved in iter_006 but the model still emitted "unknown" (e.g., DIY sealant, cocktail fifth bottle) should flip to passed.
  - Misreading/synthesis-error cluster may grow slightly because the softer prompt can cause hallucinations on low-relevance retrievals.
- Trace movement:
  - Retrieved hit metadata should show `search_mode` values reflecting dual-pass fusion (e.g., "bm25+semantic" from both full and keyword passes).
  - Fewer predictions should end with "unknown"; more should quote exact phrases from highlighted sentences.
  - Some previously empty predictions should now contain concise answers.
- Side effects to watch:
  - Token consumption should stay flat or rise modestly (+5–10%) because highlighting adds a few characters per hit but hit count limits are unchanged.
  - Runtime is negligible change (two extra BM25+cosine passes per tier).
  - Risk of 2–4 regressions where the softer prompt hallucinates an answer when retrieval is truly irrelevant.

## Falsification
- If train passrate increases by less than +0.05, the dual-pass retrieval is not rescuing the hypothesized ~25–30 retrieval-miss failures, or the RRF fusion is ineffective.
- If the abstention rate (fraction of predictions containing "unknown") does not drop by at least 10 percentage points, the prompt and highlighting changes are not changing model behavior.
- If regressions exceed 4 passed→failed tasks, the softer prompt is causing harmful hallucinations that outweigh retrieval gains.
