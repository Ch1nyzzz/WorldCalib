# iter_017 prediction

## Candidate
abstention_retry_with_broader_retrieval

## Mechanism
After the first retrieval-and-synthesis pass, if the model abstains (outputs "unknown", empty string, or phrases like "does not contain"), a second pass is triggered with doubled retrieval pool (top_k=16) and a directive synthesis prompt instructing the model to combine information across passages. The retry only fires on abstention, so already-passing tasks are unaffected.

## Outcome prediction
- Train passrate Δ: [+0.02, +0.05] (to ~0.71–0.74)
- Failure type movement: Unknown/abstain cluster should shrink by 2–4 tasks. The dominant sub-families are (1) synthesis failures where evidence is present but the model refuses to aggregate (e.g., 8cf51dda with three grant objectives, gpt4_2f91af09 with poem/story counts) and (2) partial retrieval misses where supporting docs sit just outside the top-8 pool (e.g., 60036106 missing Instagram reach). Wrong-answer count should stay flat because most wrong fails do not trigger the abstention detector.
- Trace movement: Retry traces should appear for ~20–25% of tasks (the 22/100 that abstained in iter_016). For the 2–4 tasks expected to convert, the retry trace will show a concrete answer replacing "unknown".
- Side effects to watch: Average token consumption per task should rise ~15–25% because abstaining tasks issue a second LLM call with a larger prompt. No pass regressions are expected since the retry only fires on abstention patterns that already produced fails.

## Falsification
- If passrate does not improve or regresses: the extra_instruction is too weak to overcome conservative abstention, or the max_context_chars=6000 limit renders the doubled retrieval pool ineffective (additional hits are truncated before reaching the model).
- If the unknown/abstain cluster does not shrink: the abstaining tasks are dominated by genuine retrieval misses rather than synthesis failures, so broader retrieval and directive prompting cannot help.
- If token consumption does not rise significantly: fewer tasks are hitting the abstention trigger than iter_016 suggested, or the retry logic is bypassed.
- If wrong-answer count rises: the directive to "combine information across passages" is causing hallucination on the retry pass for tasks with weak or ambiguous evidence.
