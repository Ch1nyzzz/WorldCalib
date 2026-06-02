# iter_015 prediction

## Candidate
multisignal_retrieval_without_answer_boosting

## Mechanism
The candidate adds bigram phrase overlap and character n-gram similarity to the hybrid ranker in memgpt_scaffold.py, then removes answer-signal boosting and list-atomic compression from model.py, reverting to the standard tiered contiguous-window compression (5/3/2 sentences) and the minimal synthesis prompt used in iter_012/013.

## Outcome prediction
- Train passrate Δ: [+0.00, +0.03] (to ~0.66–0.69)
- Failure type movement: Unknown/abstain cluster roughly stable (small gains from retrieval fixes offset by losing list-atomic compression benefits). Wrong-answer count should drop by 2–3 (removing list-atomic compression eliminates the 3 wrong-answer regressions observed in iter_014). Empty predictions should stay at 0–2.
- Trace movement: 3249768e and 8aef76bc should recover from "unknown" to correct (answer-signal boosting removed). 8cf51dda should recover from empty output to pass (list-atomic compression removed). 10d9b85a and gpt4_21adecb5 may show improved retrieval ranking but may still abstain if synthesis remains conservative. A few list questions that iter_014 broke through via list-atomic expansion may revert to unknown.
- Side effects to watch: Average prompt tokens should decrease slightly (no list-atomic budget expansion). No Qwen3 hidden-thinking risk because the prompt is minimal and the 1024-token budget is unchanged.

## Falsification
- If passrate drops below 0.66, multi-signal retrieval is introducing ranking noise that outweighs its lexical-variation benefits, or the loss of list-atomic compression is more destructive than expected.
- If the unknown cluster grows by more than 5 tasks, the retrieval gains from bigram/char n-grams are failing to materialize while list-atomic compression was load-bearing for more list questions than anticipated.
- If empty predictions rise above 3, the model.py reversion introduced a formatting issue or a Qwen3 prompt sensitivity not present in iter_014.
