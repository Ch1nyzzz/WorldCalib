# Fixed candidate for iteration 6

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
contiguous_window_compression

## Mechanism
Replace iter_005’s destructive list-block preservation with bounded contiguous relevance windows.

1. **Calibrated retrieval scaffold** (re-applied from iter_004): Remove arbitrary score boosts on summary/core memory, normalize RRF scores to [0,1], sort hits by score-first then tier, compact archival/recall/core formatting, and truncate archival turns to 300 chars. This is load-bearing and must be in place before any model-layer change.

2. **Contiguous relevance-window compression** (new): For each retrieved hit, split content into sentences, score each by query cosine similarity, find the peak-scoring sentence, and keep a contiguous 4-sentence window centered on that peak (±1–2 sentences). Always preserve the metadata line. Maximum 5 sentences per hit. This bounds per-hit length tightly, avoids the context-bloat that caused iter_005’s regression, and preserves local coherence better than iter_004’s scattered top-4 selection.

3. **Synthesis-permissive prompt**: Replace the overly restrictive “use exact words / do not explain reasoning” formulation with explicit permission to combine facts across passages and perform simple arithmetic/comparison when the supporting facts are present. This targets the over-abstention cluster where evidence is present but the model refuses to synthesize.

4. **512-token generation ceiling** in base.py and model.py default, with reasoning_content fallback for Qwen3 empty-content responses.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_006/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_006/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_006/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 12135 characters

