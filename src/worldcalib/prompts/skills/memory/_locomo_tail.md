---
name: worldcalib-proposer-memory-locomo-tail
description: LoCoMo memory task tail — the question_type label family and failure-mode bullets. Shared by both the locomo_calib and locomo_nowmc arms. No prediction/Upside/Downside language (that lives in the calib addon).
---

## LoCoMo task-specific hints

LoCoMo answers questions over long multi-session conversations between two
speakers. The `score_breakdown` is keyed by `question_type` — these are the
per-category breakdown keys in `candidate_results/<id>.json`, exactly:

- `single-hop` — answerable from one evidence turn;
- `multi-hop` — requires joining evidence across multiple turns/sessions;
- `temporal` — requires resolving dates / ordering / relative-time references;
- `open-domain` — requires world knowledge combined with conversation evidence.

Classify recurring failure modes from the traces and gold answers (input to a
*general* fix, never a lookup table):

- **retrieval miss** — the supporting turn was never recalled into context;
- **bad evidence ordering** — relevant turns recalled but buried or out of
  chronological order, so the model anchors on the wrong one;
- **temporal mis-resolution** — relative dates ("last summer", "two weeks ago")
  not resolved against the conversation/question date, or session ordering lost;
- **multi-hop synthesis failure** — each evidence turn recalled separately but
  not joined into the combined answer;
- **answer-format / grounding mismatch** — correct evidence in context but the
  final answer is ungrounded, over-hedged, or in the wrong shape.
