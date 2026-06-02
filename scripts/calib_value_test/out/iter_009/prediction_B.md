# iter_009 prediction

## Candidate
cross_hit_evidence_distillation

## Mechanism
The candidate layers two changes on top of iter_008's proven dual-pass retrieval, score calibration, and formatting: (1) a simplified direct-answer prompt that explicitly forbids step-by-step reasoning, reducing hidden thinking that consumes the 512-token completion budget; and (2) cross-hit evidence distillation that scores every sentence in every retrieved hit by cosine similarity to the query, extracts the top-N highest-scoring sentences across all hits, and presents them as "Relevant excerpts" at the very top of the prompt with inline provenance. The full compressed hits follow below.

This directly targets iter_008's two dominant failure families: empty/truncated outputs (10 tasks where Qwen3 consumed the completion budget in hidden thinking) and synthesis failures (a subset of the 21 unknown/abstain tasks where the answer was present in retrieved docs but buried or scattered across long passages). Front-loading the strongest evidence reduces cognitive load and makes it harder for the model to miss answer-bearing content, while the concise prompt should recover completion tokens currently lost to reasoning.

## Outcome prediction
- Train passrate Δ: [+0.04, +0.09] (to ~0.57–0.62)
- Failure type movement: The empty/truncated-output cluster should shrink from ~10 tasks to 3–5 as the simplified prompt reduces hidden thinking. The unknown/abstain cluster should shrink modestly from ~21 tasks to 15–18 as distillation surfaces buried evidence in synthesis-failure cases. Retrieval-miss failures should stay flat. Wrong-answer count should stay flat at ~7 or rise by 1–2 as more aggressive synthesis occasionally misfires.
- Trace movement: Prompt traces should show noticeably shorter system/user instructions and a new "Relevant excerpts:" block at the top of the context. Completion tokens should drop for previously empty tasks. Spans should show inline provenance markers linking excerpts to their source hits.
- Side effects to watch: Prompt token consumption may rise slightly because excerpts are added on top of full hits, potentially crowding out the lowest-ranked hit for some tasks. Risk of regressions on tasks where the answer requires cross-sentence context that gets fragmented by per-sentence extraction (e.g., temporal reasoning across multiple turns).

## Falsification
- If passrate does not improve or regresses, the simplified prompt did not reduce hidden thinking enough to offset any noise added by distillation, or the 512-token ceiling is a hard bottleneck that prompt changes cannot bypass.
- If the empty cluster stays at ~10 despite the simplified prompt, Qwen3 hidden thinking is driven by something other than prompt verbosity (e.g., a serving-layer behavior that ignores chat_template_kwargs).
- If wrong-answer count rises by more than 2, sentence-level extraction is stripping contextual guardrails and causing the model to synthesize incorrect answers from isolated excerpts.
- If prompt token consumption rises by more than ~150 tokens on average, the added excerpts are consuming context budget and displacing load-bearing hits.
