---
name: worldcalib-proposer-memory-longmemeval-tail
description: LongMemEval memory task tail — the question_type label family and failure-mode bullets. Shared by both the longmemeval_calib and longmemeval_nowmc arms. No prediction/Upside/Downside language (that lives in the calib addon).
---

## LongMemEval task-specific hints

LongMemEval answers questions over long-term, multi-session conversation
records, with an LLM judge grading the final answer. The `score_breakdown` is
keyed by `question_type` — these are the per-category breakdown keys in
`candidate_results/<id>.json`, exactly:

- `single-session-user` — answerable from one user turn in one session;
- `single-session-assistant` — answerable from one assistant turn in one session;
- `single-session-preference` — a stated user preference within one session;
- `multi-session` — requires joining evidence across multiple sessions;
- `temporal-reasoning` — requires resolving dates / ordering / relative time;
- `knowledge-update` — a fact stated then later revised; the latest value wins.

Classify recurring failure modes from the traces and gold answers (input to a
*general* fix, never a lookup table):

- **retrieval miss** — the supporting session/turn was never recalled;
- **stale knowledge-update** — answering with an outdated fact after it was
  revised in a later session (latest value not preferred);
- **cross-session join failure** — `multi-session` evidence recalled piecewise
  but not combined into the answer;
- **temporal mis-resolution** — relative/absolute dates or session ordering not
  resolved correctly;
- **judge mismatch** — answer substantively correct but phrased so the judge
  scores it wrong (ungrounded, over-hedged, or wrong granularity).
