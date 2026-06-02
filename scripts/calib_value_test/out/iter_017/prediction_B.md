# iter_017 prediction

## Candidate
abstention_retry_with_broader_retrieval

## Mechanism
After the first retrieval-and-synthesis pass, if the model abstains (empty prediction, exact "unknown", or text containing "insufficient" / "does not contain"), a second pass is triggered with doubled top_k (16 archival + 16 recall) and a slightly more directive synthesis prompt instructing cross-passage combination. The retry only fires on abstention, so already-passing tasks are unaffected. The 1024-token generation budget and 8000-character context limit are raised from the clean-snapshot defaults.

## Outcome prediction
- Train passrate Δ: [-0.34, -0.26] (to ~0.35–0.43)
- Failure type movement: The unknown/abstain cluster will grow sharply from ~18/25 to ~40–55/65–70 failures because the candidate rebuilds from the clean snapshot without restoring the proven score-calibrated, compact-formatted retrieval stack from iters 002–016. Empty predictions will shrink from ~1 to ~2–5 thanks to the 1024-token budget. Wrong answers will rise modestly to ~10–15 as the directive retry prompt occasionally pushes the model to synthesize across noisy or partial hits. The retry mechanism itself will convert only ~3–6 abstaining tasks because (a) the abstention detector is extremely narrow (it misses the common "unknown FINAL ANSWER: unknown" pattern), and (b) the clean snapshot’s uncalibrated retrieval often fails to rank gold-bearing docs into even the top-16 pool.
- Trace movement: Traces for abstaining tasks will show a second retrieval call with top_k=16 and a second LLM call carrying the extra_instruction. Most persistent failures will show gold docs ranked below the top-8 or entirely absent, with summary/core memory still dominating the hit list due to the uncalibrated +0.2/+0.1 score boosts.
- Side effects to watch: Average token consumption will rise by ~25–40% (not the predicted 20–25%) because poor retrieval produces more abstentions, triggering more second-pass LLM calls. Runtime per task will increase proportionally. A small number of previously-passing tasks could regress if their correct answer happens to contain the substring "insufficient" or "does not contain", causing an erroneous retry that introduces noise.

## Falsification
- If passrate is ≥0.55, the evaluation harness must be re-using a cached build or pre-loaded index from a previous iteration (e.g., iter_016’s memgpt_surfacing_v16) rather than rebuilding from the clean snapshot with tag memgpt_retry_v17, because the clean snapshot’s uncalibrated retrieval cannot support that passrate.
- If passrate is ≥0.65, the source snapshot must contain hidden retrieval improvements (score normalization, compact formatting, or sentence surfacing) that were not visible in the diff.
- If the empty-prediction cluster grows beyond 10 tasks, the 1024-token budget is not being applied (e.g., base.py still hardcodes 256 somewhere in the call chain).
- If wrong-answer count stays flat or shrinks despite the retry, the directive prompt is not actually increasing synthesis aggressiveness, or the retry is firing too rarely to matter.
