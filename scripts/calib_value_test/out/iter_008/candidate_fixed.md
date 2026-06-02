# Fixed candidate for iteration 8

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
keyword_augmented_dual_pass_retrieval

## Mechanism
The dominant failure family in iter_006 is retrieval misses: ~25-30 of the 50 failures have no gold-bearing documents in the top retrieved set. The current BM25+cosine search uses the full question text, which includes diluting stopwords ("I've", "been", "thinking", "about", "did", "the", etc.). These filler words dilute the lexical signal and cause the search to miss documents that share content words but not the full phrasing.

The new candidate adds a keyword-augmented dual-pass retrieval layer: for each tier (archival and recall), we run the hybrid ranker twice — once with the full query tokens and once with stopwords removed — then fuse the two rankings with RRF. This increases the chance of surfacing documents that match the core content words even when they don't match the full query phrasing. We also add focal sentence highlighting (wrapping the peak-relevance sentence in `** **` markers inside each compressed hit) to help the model attend to the most answer-bearing region, and we soften the system prompt to explicitly permit synthesis across passages and to only abstain when truly no relevant information is present.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_008/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_008/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_008/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 18923 characters

