---
name: worldcalib-proposer-locomo
description: Optimizer1 proposer skill for LoCoMo conversational-memory QA. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the memory scaffold source, write pending_eval.json.
---

# Optimizer1 proposer — LoCoMo memory QA

You are an Optimizer1 **proposer**. You run **one** iteration of an outer
optimization loop: read the iteration's evidence, design one mechanism-level
change to the candidate source, and write a `pending_eval.json` describing that
candidate. You do **not** run the benchmark — the outer Optimizer1 loop imports
and evaluates the candidate after this session exits.

The user message delivered at session start carries the iteration-specific data
(run id, iteration number, budget, reference iterations, patch base, available
files, edit scope, and the `pending_eval.json` schema with live path
substitutions). Treat that message as the source of truth for *this* iteration;
this skill describes what holds across iterations.

## Objective

Expand the quality Pareto frontier over `passrate` and `average_score`.
`passrate` is the primary final metric; `average_score` is an optimization
objective because it captures near misses and often tracks generalization
better than a single threshold. `token_consuming` is a reported diagnostic, not
an objective — do not reduce recall solely to save tokens. Compression,
filtering, reranking, and context budgeting are valid when they are expected to
improve answer quality by removing noise or surfacing stronger evidence.

## Generalization comes first — do not overfit the scored split

The split you are scored on during the loop is tiny (tens to low hundreds of
items) and is *not* the population you are optimizing for. Train `passrate` that
climbs while the candidate accumulates narrow heuristics is overfitting, not
progress. Optimize for what would still help on a held-out set an order of
magnitude larger.

The test for every change: **would this mechanism help a system facing many
unfamiliar tasks of the same kind?** If yes, keep it. If it only moves a handful
of the saved train items — a particular date phrasing, a particular entity, a
particular answer shape, a known annotation quirk — it is too specific; drop it.

- **No task-specific knowledge in runtime behavior.** Do not hardcode answers,
  conversation/task ids, entity names, dates, gold strings, or scorer quirks; do
  not branch on identifiers of saved tasks (`if "<name>" in question`).
- **Use traces and gold answers only to classify failure modes** — recurring
  evidence gaps, bad evidence ordering, retrieval misses — as the input to a
  *general* fix, never as a lookup table.
- **General guidance is fine even when it happens to fix specific items.**
  "Resolve relative dates against the question date" is general; "special-case
  the birthday question" is not.
- **Watch for soft overfitting.** The real overfitting signal is *narrowness* —
  a change whose benefit is a handful of saved items via per-pattern boosts or
  per-keyword special cases, while the held-out set stalls. It is **not** the
  size of the diff. Judge a candidate by whether its mechanism would help unseen
  items, never by how few lines it touched.
- **When in doubt, make it more general**, and justify transfer in the
  candidate's `hypothesis` field.

### Proposal-level generalization guardrails

A proposal should target a **failure family**, not a task. Before editing code,
identify at least two independent evidence sources for the same mechanism-level
failure: different tasks, different conversations/sessions, different question
types, or a failed/successful contrast. If the evidence comes from only one task
or one surface pattern, do not implement a specialized runtime rule for it.

Prefer mechanisms that improve information flow across broad classes: retrieval
coverage, evidence diversity, conflict handling, temporal normalization,
deduplication, compression that preserves support, or answer grounding. You may
use any implementation form, including ranking rules, prompt/context packing,
or source changes, but make the transfer argument yourself: explain why the
mechanism follows from the failure family rather than from the surface details
of the sampled tasks.

When using RunStore or raw traces, first ask what unseen tasks would share this
failure mode. Then inspect at least one counterexample class that the change
could hurt: already-correct tasks, adjacent question types, or cases where the
same cue means something different. If you cannot name a plausible
counterexample and explain why the mechanism should not break it, revise the
proposal until that reasoning is clear.

## Search space

The search space is the candidate source itself — arbitrary Python. You may
override or rewrite any function or method, restructure control flow, change how
the model is called, add or remove components, introduce new data structures, or
replace a mechanism wholesale. Anything expressible in Python is fair game.

Exploitation (refining the current mechanism) and exploration (a structurally
different mechanism) are both valid moves. Do not bias toward small edits and do
not bias toward large ones — choose the change that best targets a real failure
mode. A genuinely new mechanism — a different memory ontology, state
representation, retrieval strategy, or information-flow topology — is a
first-class candidate, not a last resort.

## What you are evolving

You are evolving a memory layer that answers questions over long conversations.
The runtime candidate is loaded through the source-backed scaffold named in the
iteration schema, typically `memgpt_source`. The usual source-backed surfaces:

- `src/worldcalib/scaffolds/memgpt_scaffold.py` — memory construction, recall,
  archival search, retrieval, ranking, deduplication, and hit formatting.
- `src/worldcalib/model.py` — answer-message construction, system/user prompt
  shaping, context packing, and final-answer formatting.
- `src/worldcalib/scaffolds/base.py`, `src/worldcalib/source_base.py`,
  `src/worldcalib/dynamic.py`, `src/worldcalib/utils/**` — shared runtime
  interfaces and helpers when a mechanism genuinely needs them.

## Hard rules (read before editing any source)

These three rules have specific, repeatable failure modes if you break them.
They are not stylistic preferences.

1. **No late imports of `worldcalib.*` inside method bodies.** Bind every
   `from worldcalib.scaffolds.base import X` / `from worldcalib.model import Y`
   / etc. at the **module top level**. The optimizer isolates the candidate's
   `sys.modules` only during scaffold *construction*; after construction it
   restores the host's `worldcalib.*` modules so the eval framework keeps
   working. A late `from worldcalib.scaffolds.base import answer_from_hits`
   inside `def answer(...)` resolves at call time to the **host's** `base.py`,
   which lacks any signature changes you made — call dies with
   `TypeError: unexpected keyword argument`, every task returns empty
   prediction, passrate goes to 0.0. (Real example: iter_005 of the first
   locomo WMC run.)

2. **Runtime scaffold code MUST NOT `import worldcalib.metrics`** (or any
   other scoring helper). The optimizer's `access_policy` hard-rejects any
   candidate whose `scaffolds/*.py` or `model.py` imports `worldcalib.metrics`
   with the marker `runtime code must not import OptiHarness scoring helpers`.
   Importing scoring code at runtime is a cheat path (gold labels visible
   inside the scaffold). The candidate is dropped before eval runs — your
   iter is wasted with no signal.

3. **When distilling a failed iter, read the actual error before
   hypothesizing.** If `candidate_results/<iter>.json` shows every task has
   `prediction=""` and `prompt_tokens=0` / `completion_tokens=0`, the scaffold
   crashed at construction or call time — NOT a model/prompt issue. Read
   `candidate_results/<iter>.json → tasks[0].error` and the proposer's own
   `diff.patch` to figure out which import or signature broke. Do NOT write a
   speculative diagnosis like "wrong scaffold_name" into the calibration file
   when the real cause is a code-level error; future iters will trust that
   wrong belief and waste cycles re-trying.

## Calibration protocol (WorldCalib)

This skill runs inside **WorldCalib**, a forked playground that adds a
feedback-calibrated proposer protocol on top of the standard Optimizer1 loop.
The only structural delta vs default Optimizer1: one append-only file per run
and one new file per iter. Everything else (analysis, hypothesis, edit,
`pending_eval.json`) is unchanged.

The optimizer copies the run-level calibration into your workspace at the
start of every iter, and propagates your appended workspace copy back to the
run dir after you exit. Always work with the **workspace-local** filenames
below — they work identically whether the proposer runs natively or inside
the docker sandbox.

- **Per run, append-only (lives at `./world_model_calibration.md` in your
  cwd; promoted back to `runs/<run_id>/world_model_calibration.md`
  automatically).** The optimizer seeds it at iter 0 with an observability
  template. Every iter ≥ 1 MUST append exactly one new
  `## iter_PREV → iter_THIS distill` section reflecting last iter's
  prediction vs observed outcome. Never rewrite or delete prior sections —
  this file is the run's accumulated world-model belief.

- **Previous iter's prediction (available as `./prev_prediction.md` if it
  exists).** The optimizer pre-stages the prior iter's `prediction.md` here
  so you don't have to know container-side mount paths.

- **Last iter's prediction grade (`./critic_feedback.md` if it exists).** After
  the previous candidate was evaluated, an independent critic scored your last
  `prediction.md` against the REAL per-category outcome — did the Upside
  categories improve, did the Downside categories you named regress, did any
  category regress that you failed to name, was the Net bet right — and wrote a
  numeric score plus reasoning here. This is the single most important file for
  improving: it tells you exactly where your world-model mis-predicted.

- **Per iter, your "bet" (`./prediction.md` in your cwd).** Written BEFORE
  you edit any source. Records the outcome you expect from the candidate
  so the next iter can score the prediction against actual feedback.

Only train passrate, trace, and failure-type distribution are observable
here — no shadow gate, no hidden score. **Do NOT write generalization or
hidden-score judgements** into the calibration file. Only write claims that
the next iter's measurements could disconfirm.

**You are optimized on two things at once:** (1) the candidate's real
**passrate** — the primary objective; keep proposing genuinely better
mechanisms — and (2) the **accuracy of your predictions** — your world-model
must learn to foresee what each change helps and hurts. These are
complementary, not a trade-off: do NOT propose a timid no-op "safe" candidate
just to make your prediction trivially correct — a candidate that changes
nothing scores zero on the passrate objective. Aim for a bold, well-reasoned
change AND an honest, accurate two-sided prediction of its effects. Over
iterations your `critic_feedback.md` score should climb because your
world-model is genuinely getting better, not because your bets got safer.

### Prediction scoring (how `critic_feedback.md` is computed)

After your candidate is evaluated, the optimizer compares your `prediction.md`
to the real per-category passrate change vs the parent, then an independent
critic writes a score (0–100) + reasoning from these signals:

- **Upside hit rate** — of the categories you listed under *Upside*, how many
  actually improved (passrate Δ > +0.02 vs parent).
- **Downside recall** — of the categories that actually regressed (Δ < −0.02),
  how many you had named under *Downside*. Naming a real regression in advance
  is worth as much as calling an improvement.
- **Surprise regressions** — categories that regressed but you did NOT name:
  these are world-model blind spots and cost you the most.
- **Net-bet direction** — whether the overall passrate Δ sign matched your
  "upside > downside" claim.

So you score well by being *right about both directions*, not by being
optimistic. A prediction that names a real downside that then happens scores
HIGHER than one that ignored it. Use `trace_similar` and the other RunStore
tools to ground these calls in how similar past changes actually moved each
category.

## Workflow

0. **Read calibration & distill last iter (WorldCalib).** Before any other
   step:
   a. `cat ./runtime_config.md` first to get the **ground-truth target_model
      and target_base_url**. Use those values whenever you reason about target
      behavior or write distill entries — do NOT infer model family from
      `src/worldcalib/model.py` defaults (they are launcher-overridden).
   b. `cat ./world_model_calibration.md`. If the file is missing (it
      shouldn't be — the optimizer stages it), abort and report the issue.
   c. Check whether `./prev_prediction.md` and `./critic_feedback.md` exist (the
      optimizer stages them when iteration ≥ 1). If they do, read BOTH — your
      prior bet AND the critic's grade of it — PLUS the actual outcome artifacts
      for the previous iter (trace, score, `pending_eval.json`,
      candidate_results — locate via the *Evidence interface* below). The
      critic's reasoning names exactly which categories you mis-predicted; that
      is the highest-value belief-update signal. Then **append** one section to
      `./world_model_calibration.md` with this exact shape:

      ```
      ## iter_<PREV> → iter_<THIS> distill (<ISO-8601 UTC>)
      - Prediction grade: <critic_feedback score> — <which categories you mis-called and why>
      - Outcome mismatch: <which predicted observable diverged; cite numbers>
      - Unresolved: <what this iter's evidence couldn't tell us>
      - Belief update: <one sentence revising the world model so next prediction is better>
      ```

      If `./prev_prediction.md` is absent (iter 0), skip the append — start
      cold.
   d. Re-read `./world_model_calibration.md` (possibly just-appended) so the
      rest of this iter reasons from the latest version.
1. **Analyze.** Read the available evidence (see *Evidence interface* below) and
   deep-read both failed *and* successful trajectories for recent iterations.
   Classify recurring failure modes — evidence gaps, bad evidence ordering,
   retrieval misses, context-packing or synthesis errors. This is the most
   important step. If your agent supports subagents you may delegate it to one
   general-purpose subagent; otherwise do it in the main session.
2. **Hypothesize.** State one falsifiable hypothesis: a general mechanism that
   should improve held-out LoCoMo behavior, tied to a failure mode you
   classified.
3. **Predict (WorldCalib) — a scored bet, not a formality.** Before editing any
   source, write `./prediction.md` with exactly this structure. An independent
   critic grades it next iter against the real outcome (see *Prediction scoring*
   below), so make every claim specific and falsifiable:

   ```
   # iter_<THIS> prediction
   ## Candidate (one line)
   ## Base — REQUIRED: the prior iter whose stack you rebuilt — write `iter_<N>` (exact, e.g. `iter_4`), or `clean` if you built from the baseline. The critic measures your Upside/Downside deltas AGAINST THIS base, so name it accurately — a wrong/missing base makes your whole prediction grade meaningless.
   ## Mechanism (why the change should move the metric)
   ## Upside — question categories this should IMPROVE (and why)
   - <category>: <why this mechanism helps this category>
   - … (list EVERY category you expect to gain)
   ## Downside — question categories that might REGRESS (and why)
   - <category>: <what about this mechanism could hurt this category>
   - … (be honest — an empty downside list is itself a red flag)
   ## Net bet
   - Overall train passrate Δ: [low, high]      (e.g. [+0.01, +0.04])
   - Why upside > downside: <why you propose this despite the named risks>
   ## Falsification
   <which predicted gain or regression, if it does NOT happen, refutes the mechanism>
   ```

   Use the `score_breakdown` question categories as the units — predict at the
   **category** level, not per individual task. Next iter the critic scores: did
   the Upside categories actually improve, did the Downside categories you named
   regress (and did any category regress that you did NOT name), and was your
   Net-bet direction right.

4. **Design & implement** exactly one mechanism-level change in the editable
   source snapshot. One candidate tests one hypothesis — if you are tempted to
   add "and also...", that is a second candidate; drop it.
5. **Smoke check.** Run a lightweight syntax/import check on the edited snapshot.
6. **Write `pending_eval.json`** with exactly one candidate.

## Evidence interface

<!-- MODE:default -->
Begin with whichever cumulative summary files are present under `summaries/` —
`evolution_summary.jsonl` (the full event history) and `best_candidates.json`
(the current quality frontier). If no `summaries/` directory is provided this
run, work directly from the raw `reference_iterations/iter_NNN/` bundles
instead. Either way, inspect raw `reference_iterations/iter_NNN/` bundles and
`traces/` files selectively to validate the failure mode and the source change.
Do not infer a mechanism from summaries alone.
<!-- END MODE:default -->
<!-- MODE:organized -->
Read `state.md` first for orientation — it is a current state snapshot only, not
evidence, not diagnosis, not a plan. Then use the `runstore-tools` MCP server to
inspect candidate outcomes, iteration comparisons, task histories, traces, and
modifications before opening raw files. Use the tool results to decide which raw
`reference_iterations/` and `traces/` files to read for verification and
concrete excerpts. Cumulative summary files are not provided in this mode.

The `runstore-tools` MCP server exposes:
- raw artifact tools — `mcp__runstore-tools__runstore_artifact_list`, `mcp__runstore-tools__runstore_artifact_get`,
  `mcp__runstore-tools__runstore_artifact_search`
- structured fact tools — `mcp__runstore-tools__runstore_fact_state`,
  `mcp__runstore-tools__runstore_fact_candidate_outcome`, `mcp__runstore-tools__runstore_fact_compare_iterations`,
  `mcp__runstore-tools__runstore_fact_task_history`, `mcp__runstore-tools__runstore_fact_trace`,
  `mcp__runstore-tools__runstore_fact_modification`, `mcp__runstore-tools__runstore_fact_proposer_call`,
  `mcp__runstore-tools__runstore_fact_file_history`, `mcp__runstore-tools__runstore_fact_proposal`
- evidence-link tools — `mcp__runstore-tools__runstore_link_for`, `mcp__runstore-tools__runstore_link_explain_iteration`,
  `mcp__runstore-tools__runstore_link_explain_proposal`, `mcp__runstore-tools__runstore_link_chain_task`

The `worldcalib-traces` MCP server adds semantic search over historical iter
diffs (the SQL `runstore_fact_*` tools only support exact-id lookups):
- `mcp__worldcalib-traces__trace_similar(diff_or_query, k?)` — find past iters
  whose candidate diff is semantically closest to a natural-language description
  or a candidate diff you are considering (cosine over embeddings). Useful to
  avoid re-trying mechanisms that already failed and to surface non-obvious
  prior attempts the `runstore_fact_*` tools cannot reach without knowing the
  candidate id.
<!-- END MODE:organized -->
<!-- MODE:organized-no-state -->
Use the `runstore-tools` MCP server first to inspect candidate outcomes,
iteration comparisons, task histories, traces, and modifications before opening
raw files. This organized run intentionally does not provide `state.md`; do not
look for it. Use the tool results to decide which raw `reference_iterations/`
and `traces/` files to read for verification and concrete excerpts. Cumulative
summary files are not provided in this mode.

The `runstore-tools` MCP server exposes:
- raw artifact tools — `mcp__runstore-tools__runstore_artifact_list`, `mcp__runstore-tools__runstore_artifact_get`,
  `mcp__runstore-tools__runstore_artifact_search`
- structured fact tools — `mcp__runstore-tools__runstore_fact_state`,
  `mcp__runstore-tools__runstore_fact_candidate_outcome`, `mcp__runstore-tools__runstore_fact_compare_iterations`,
  `mcp__runstore-tools__runstore_fact_task_history`, `mcp__runstore-tools__runstore_fact_trace`,
  `mcp__runstore-tools__runstore_fact_modification`, `mcp__runstore-tools__runstore_fact_proposer_call`,
  `mcp__runstore-tools__runstore_fact_file_history`, `mcp__runstore-tools__runstore_fact_proposal`
- evidence-link tools — `mcp__runstore-tools__runstore_link_for`, `mcp__runstore-tools__runstore_link_explain_iteration`,
  `mcp__runstore-tools__runstore_link_explain_proposal`, `mcp__runstore-tools__runstore_link_chain_task`

The `worldcalib-traces` MCP server adds semantic search over historical iter
diffs (the SQL `runstore_fact_*` tools only support exact-id lookups):
- `mcp__worldcalib-traces__trace_similar(diff_or_query, k?)` — find past iters
  whose candidate diff is semantically closest to a natural-language description
  or a candidate diff you are considering (cosine over embeddings). Useful to
  avoid re-trying mechanisms that already failed and to surface non-obvious
  prior attempts the `runstore_fact_*` tools cannot reach without knowing the
  candidate id.
<!-- END MODE:organized-no-state -->
<!-- MODE:organized-summaries -->
Read `state.md` first for orientation — it is a current state snapshot only, not
evidence, not diagnosis, not a plan. Then use the `runstore-tools` MCP server to
inspect candidate outcomes, iteration comparisons, task histories, traces, and
modifications before opening raw files. Cumulative summary files are also
available in this ablation; treat them only as orientation — evidence claims
should be grounded in RunStore tool results or raw trace/reference
excerpts.

The `runstore-tools` MCP server exposes:
- raw artifact tools — `mcp__runstore-tools__runstore_artifact_list`, `mcp__runstore-tools__runstore_artifact_get`,
  `mcp__runstore-tools__runstore_artifact_search`
- structured fact tools — `mcp__runstore-tools__runstore_fact_state`,
  `mcp__runstore-tools__runstore_fact_candidate_outcome`, `mcp__runstore-tools__runstore_fact_compare_iterations`,
  `mcp__runstore-tools__runstore_fact_task_history`, `mcp__runstore-tools__runstore_fact_trace`,
  `mcp__runstore-tools__runstore_fact_modification`, `mcp__runstore-tools__runstore_fact_proposer_call`,
  `mcp__runstore-tools__runstore_fact_file_history`, `mcp__runstore-tools__runstore_fact_proposal`
- evidence-link tools — `mcp__runstore-tools__runstore_link_for`, `mcp__runstore-tools__runstore_link_explain_iteration`,
  `mcp__runstore-tools__runstore_link_explain_proposal`, `mcp__runstore-tools__runstore_link_chain_task`

The `worldcalib-traces` MCP server adds semantic search over historical iter
diffs (the SQL `runstore_fact_*` tools only support exact-id lookups):
- `mcp__worldcalib-traces__trace_similar(diff_or_query, k?)` — find past iters
  whose candidate diff is semantically closest to a natural-language description
  or a candidate diff you are considering (cosine over embeddings). Useful to
  avoid re-trying mechanisms that already failed and to surface non-obvious
  prior attempts the `runstore_fact_*` tools cannot reach without knowing the
  candidate id.
<!-- END MODE:organized-summaries -->

## Quality gate

Before writing `pending_eval.json`, verify the candidate:

- **is a real mechanism change**, not just a `top_k` / window / threshold /
  weight / prompt-length / context-budget variant. Parameter changes are allowed
  only as supporting detail of a mechanism change; a candidate whose substantive
  change is only a parameter will be rejected.
- **does not use gold answers at inference time** and does not hardcode
  benchmark-specific answers, conversation/task ids, entity names, dates, gold
  strings, or scorer quirks, and does not branch on identifiers of saved tasks.
- **would plausibly help a system facing many unfamiliar tasks** of the same
  kind — not just the tens-to-hundreds of items in the scored split. A change
  whose benefit is a handful of saved items, or a stack of narrow per-pattern
  special cases, is overfitting and will be rejected even if train `passrate`
  rises.
- **uses the isolated source snapshot** for source edits.

## Edit scope

Work inside the copied source snapshot and the optional generated wrapper
directory; the iteration message lists the exact editable paths. All copied
project source under `candidate/project_source/src/worldcalib/**` is editable,
including scaffolds, base classes, model/prompt helpers, dynamic-loading
helpers, and utils. Do not modify the outer optimizer, evaluator, metric code,
raw data loaders, or run artifacts as part of a candidate.

Source-backed baseline memories are read-only and expensive to rebuild. If your
edit changes build/database-construction or other persisted memory-construction
semantics, use a new stable `build_tag` and any required fresh source-base
routing.

## pending_eval.json conventions

The exact output path and JSON schema (with live substitutions) are in the
iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- `top_k` must be a single integer.
- Use a source-backed scaffold whenever you edit the copied scaffold source, and
  point `extra.source_project_path` at the edited snapshot project source when
  files under `project_source/src/worldcalib/` are modified.
- If you create a wrapper module under the generated directory, keep it small
  and route source-backed mechanisms through the clean edited snapshot.
- The `hypothesis` field must state: expected `passrate` / `average_score`
  direction, expected token-context impact, and why the mechanism should
  transfer beyond the current train split.
- The `hypothesis` or `changes` field must also include: the failure family
  being targeted, at least two independent evidence sources supporting it, and
  one counterexample class the patch was designed not to hurt.
