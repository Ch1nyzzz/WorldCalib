# iter_008 prediction

## Candidate
keyword_augmented_dual_pass_retrieval

## Mechanism
The dominant failure family in iter_006 is retrieval misses: ~25-30 of the 50 failures have no gold-bearing documents in the top retrieved set. The current BM25+cosine search uses the full question text, which includes diluting stopwords ("I've", "been", "thinking", "about", "did", "the", etc.). These filler words dilute the lexical signal and cause the search to miss documents that share content words but not the full phrasing.

The new candidate adds a keyword-augmented dual-pass retrieval layer: for each tier (archival and recall), we run the hybrid ranker twice — once with the full query tokens and once with stopwords removed — then fuse the two rankings with RRF. This increases the chance of surfacing documents that match the core content words even when they don't match the full query phrasing. We also add focal sentence highlighting (wrapping the peak-relevance sentence in `** **` markers inside each compressed hit) to help the model attend to the most answer-bearing region, and we soften the system prompt to explicitly permit synthesis across passages and to only abstain when truly no relevant information is present.

## Outcome prediction
- Train passrate Δ: [+0.05, +0.12] (to ~0.55–0.62)
- Failure type movement: The "unknown with irrelevant retrieved docs" cluster should shrink as keyword-augmented retrieval surfaces more relevant passages. The "unknown despite relevant docs" synthesis cluster should also shrink due to focal highlighting and more permissive prompt instructions. Wrong-answer count should stay flat or slightly increase (risk of the more permissive prompt).
- Trace movement: Retrieved documents for previously failed tasks should show higher topical relevance. Spans should show dual-query fusion in metadata.
- Side effects to watch: Token consumption may rise slightly if broader retrieval brings in more total hits before compression; completion tokens should stay stable. Risk of regressions on tasks where stopword removal changes query semantics (e.g., negation-heavy questions).

## Falsification
- If passrate does not improve or regresses, the dual-query mechanism may be retrieving more noise than signal, or the stopword filter may be too aggressive.
- If the "unknown" cluster stays flat while retrieved doc relevance improves, the prompt-induced abstention is the real bottleneck and retrieval changes were secondary.
- If wrong-answer count increases significantly, the softer synthesis prompt is causing hallucination.
