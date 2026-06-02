# iter_017 prediction

## Candidate
abstention_retry_with_broader_retrieval

## Mechanism
The dominant remaining failure family is unknown/abstain (~18/25 failures in iter_016). This cluster splits into two sub-families:
1. Synthesis failures where evidence is present but the model abstains conservatively. Two independent evidence sources: (a) gpt4_2f91af09 — the retrieved docs explicitly mention "17 poems", "five short stories", and "one writing challenge piece", yet the model refuses to aggregate them into 23; (b) 8cf51dda — the top retrieved doc contains all three grant objectives in a numbered list, yet the model claims only two are present.
2. Partial retrieval misses where the initial top-8 pool contains some evidence but misses supporting docs. Evidence: 129d1232 finds $5,000 + $250 but gold is $5,850, indicating other charity event docs are missing; 60036106 finds Facebook 2,000 reach but misses the Instagram influencer doc needed for the 12,000 total.

The new mechanism is an abstention-triggered retry: after the first retrieval-and-synthesis pass, if the model outputs "unknown", an empty string, or a clear abstention phrase, a second pass is triggered with (a) a doubled retrieval pool (top_k=16 archival + 16 recall) to increase coverage, and (b) a slightly more directive synthesis prompt that explicitly instructs the model to combine information across passages. The retry only fires on abstention, so already-passing tasks are unaffected. The 1024-token generation budget and minimal prompt are kept as load-bearing infrastructure.

## Outcome prediction
- Train passrate Δ: [+0.03, +0.06] (to ~0.72–0.75)
- Failure type movement: Unknown/abstain cluster should shrink by 3–5 tasks (synthesis failures where the directive prompt helps, plus partial retrieval misses where the broader pool brings in the missing doc). Wrong answers should stay flat or rise by at most 1 (risk of hallucination from noisy broader retrieval). Empty predictions should stay at ~1.
- Trace movement: For previously failed synthesis tasks, the second-pass prediction should be a concrete answer rather than "unknown". For partial retrieval misses, the second retrieval should surface additional hits not present in the first pass.
- Side effects to watch: Token consumption rises ~20–25% because ~25% of tasks trigger a second model call. Risk of timeout if the second call is slow. Risk of regression on genuinely-unanswerable tasks if the broader retrieval brings in conflicting noise and the directive prompt pushes the model to hallucinate.

## Falsification
- If passrate does not improve or regresses, the unknown cluster is dominated by genuine retrieval misses where the broader pool still does not contain the gold doc, or the directive prompt causes hallucinations on ambiguous tasks.
- If wrong-answer count rises by more than 1, the broader retrieval is adding noisy/conflicting docs that the directive prompt overweights.
- If empty predictions increase, the second prompt is triggering Qwen3 hidden thinking.
