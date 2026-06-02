# Fixed candidate for iteration 17

This candidate has ALREADY been decided and implemented. It is the
exact change that was evaluated this iteration. Predict ITS outcome —
do not design a different candidate.

## Candidate
abstention_retry_with_broader_retrieval

## Mechanism
The dominant remaining failure family is unknown/abstain (~18/25 failures in iter_016). This cluster splits into two sub-families:
1. Synthesis failures where evidence is present but the model abstains conservatively. Two independent evidence sources: (a) gpt4_2f91af09 — the retrieved docs explicitly mention "17 poems", "five short stories", and "one writing challenge piece", yet the model refuses to aggregate them into 23; (b) 8cf51dda — the top retrieved doc contains all three grant objectives in a numbered list, yet the model claims only two are present.
2. Partial retrieval misses where the initial top-8 pool contains some evidence but misses supporting docs. Evidence: 129d1232 finds $5,000 + $250 but gold is $5,850, indicating other charity event docs are missing; 60036106 finds Facebook 2,000 reach but misses the Instagram influencer doc needed for the 12,000 total.

The new mechanism is an abstention-triggered retry: after the first retrieval-and-synthesis pass, if the model outputs "unknown", an empty string, or a clear abstention phrase, a second pass is triggered with (a) a doubled retrieval pool (top_k=16 archival + 16 recall) to increase coverage, and (b) a slightly more directive synthesis prompt that explicitly instructs the model to combine information across passages. The retry only fires on abstention, so already-passing tasks are unaffected. The 1024-token generation budget and minimal prompt are kept as load-bearing infrastructure.

## Actual code change (diff digest)

# Diff Digest

Changed files:
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_017/source_snapshot/candidate/project_source/src/worldcalib/model.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_017/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/base.py
- runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607/proposer_calls/iter_017/source_snapshot/candidate/project_source/src/worldcalib/scaffolds/memgpt_scaffold.py

Patch size: 8100 characters

