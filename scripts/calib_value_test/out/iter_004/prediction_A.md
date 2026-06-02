# iter_004 prediction

## Candidate
query_focused_semantic_compression

## Mechanism
Query-focused semantic sentence compression layered on calibrated retrieval ranking and a 512-token generation budget.

1. **Retrieval score calibration** (supporting infrastructure): Remove arbitrary score boosts (+0.1 core, +0.2 summary), normalize RRF scores to [0,1], sort hits purely by relevance score, and compact archival/recall formatting. This restores the retrieval quality that iter_002 proved was load-bearing and that iter_003 catastrophically lost.

2. **Query-aware per-hit sentence compression** (novel mechanism): After retrieval, each hit is compressed by keeping only the 4 sentences most semantically relevant to the query (cosine similarity over tokens), preserving the first line as metadata and restoring original sentence order. This maximizes evidence density: more distinct hits fit in the 6000-char context budget, and the model sees less noise per hit.

3. **Generation budget liberation**: Fix the hidden base.py max_tokens=256 hardcode to 512, add reasoning_content fallback for Qwen3, and keep a concise direct-answer prompt.

## Outcome prediction
- Train passrate Δ: [+0.10, +0.20] (from iter_002’s 0.47 baseline to ~0.57–0.67)
- Failure type movement:
  - "unknown" cluster shrinks by 8–15 (gold evidence is now more salient within compressed hits)
  - "empty" cluster shrinks from ~25 to <5 (512-token budget removes truncation)
  - "wrong_answer" cluster stable or shrinks slightly (better evidence focus reduces picking wrong passages)
- Trace movement:
  - Completion tokens exceed 256 for many previously empty tasks
  - Prompt context includes more hits (8–12 vs 4–6) because each hit is shorter
  - Predictions more often use exact words from context
- Side effects to watch:
  - Prompt tokens may rise slightly from more included hits
  - Risk of dropping relevant cross-sentence context in rare cases where the answer spans >4 sentences in one hit

## Falsification
- Passrate below 0.52 would suggest sentence compression hurts coherence or that ranking calibration is insufficient
- Empty predictions remaining ≥10 would indicate the 512-token budget is still inadequate for some task types
- "unknown" cluster not shrinking would mean the dominant failure is retrieval miss (gold not in top-K) rather than evidence salience
