---
name: worldcalib-proposer-locomo-critic
description: WorldCalib proposer skill for LoCoMo (ledger + adversarial-critic variant). Runs one optimization iteration — analyze evidence, design one mechanism-level change, then submit the candidate to an adversarial reference-class critic subagent grounded in the RunStore ledger before writing pending_eval.json. No prose calibration file.
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

3. **When a prior iter failed, read the actual error before hypothesizing.**
   If `candidate_results/<iter>.json` shows every task has `prediction=""` and
   `prompt_tokens=0` / `completion_tokens=0`, the scaffold crashed at
   construction or call time — NOT a model/prompt issue. Read
   `candidate_results/<iter>.json → tasks[0].error` and that iter's `diff.patch`
   to figure out which import or signature broke. A code-level crash is an
   implementation bug, not a world-model signal: do not let it masquerade as a
   mechanism-level lesson. Use the RunStore ledger (below) for what actually
   moved the metric, and a lightweight smoke check (workflow step 5) to catch
   crashes before eval.

## World model = the RunStore ledger (WorldCalib — ledger + critic variant)

This skill runs inside **WorldCalib**. Unlike the prose-calibration variant,
**there is no `world_model_calibration.md` and no distill step.** The world
model is the **RunStore ledger** — the `runstore.db` the optimizer writes
automatically after every eval. It is the only world model that does not lie,
because it is measured, not narrated. You do not maintain it; you *query* it
(via the RunStore tools in the *Evidence interface* below) and you are *held
to it* by an adversarial critic before your candidate is accepted.

What the ledger already records for every past iter — query it, do not
re-derive it from prose:

- the candidate's diff, its `passrate` and `average_score`;
- its outcome **relative to its parent**: `passrate_delta`, `regression_count`,
  `breakthrough_count` (i.e. did it regress, and by how much / on how many
  tasks);
- per-task pass/fail and trace spans.

`trace_similar(your draft diff or description, k)` returns the **reference
class**: the historically most similar candidates and their real outcomes.
That base rate — *"of the k candidates most like mine, how many regressed"* —
is the prior your prediction must be anchored to. This is what replaces the
accumulated prose belief: a fresh, candidate-specific, measured base rate
fetched at proposal time.

Per-iter files (workspace-local; work identically native or in the docker
sandbox):

- **`./prediction.md` — your "bet"**, written BEFORE you edit source. Includes
  an explicit `P(regress)`. The optimizer scores it automatically against the
  ledger after eval; **you never distill it by hand.**
- **`./critique.md` — the critic subagent's adversarial review** (workflow
  step 3.5). Mandatory; `pending_eval.json` is rejected without it.
- **`./calibration_track_record.md` — your own scored history**, staged by the
  optimizer if available. It reports how well your past `P(regress)` calls
  matched reality (Brier, directional bias). Read it and **correct your own
  optimism** — if it says you systematically under-call regressions on a class
  of change, raise your `P(regress)` for that class this iter.

Only train passrate, trace, and failure-type distribution are observable here —
no shadow gate, no hidden score.

## Workflow

0. **Orient against the ledger & your own track record (WorldCalib).** Before
   any other step:
   a. `cat ./runtime_config.md` first to get the **ground-truth target_model
      and target_base_url**. Use those values whenever you reason about target
      behavior — do NOT infer model family from `src/worldcalib/model.py`
      defaults (they are launcher-overridden).
   b. If `./calibration_track_record.md` exists, read it: it is the optimizer's
      mechanical scoring of your past `P(regress)` calls against real outcomes
      (Brier score, directional bias). Note any systematic bias — e.g.
      "under-calls regressions on retrieval-only changes" — and carry the
      correction into this iter's prediction.
   c. Do **not** hand-distill anything and do **not** look for
      `world_model_calibration.md` — this variant has none. Last iter's
      prediction was already scored against the ledger automatically; the
      lesson lives in the ledger (query it via the *Evidence interface*) and in
      your track record, not in a prose file you append to.
1. **Analyze.** Read the available evidence (see *Evidence interface* below) and
   deep-read both failed *and* successful trajectories for recent iterations.
   Classify recurring failure modes — evidence gaps, bad evidence ordering,
   retrieval misses, context-packing or synthesis errors. This is the most
   important step. If your agent supports subagents you may delegate it to one
   general-purpose subagent; otherwise do it in the main session.
2. **Hypothesize.** State one falsifiable hypothesis: a general mechanism that
   should improve held-out LoCoMo behavior, tied to a failure mode you
   classified.
3. **Predict (WorldCalib).** Before editing any source, write `./prediction.md`
   in this iter's workspace with exactly this structure:

   ```
   # iter_<THIS> prediction
   ## Candidate (one line)
   ## Mechanism (why the change should move the metric)
   ## Outcome prediction
   - Train passrate Δ: [low, high]         (e.g. [+0.005, +0.020])
   - P(regress): <0.00–1.00>               (probability final passrate < parent)
   - Failure type movement: <which clusters shrink / grow>
   - Trace movement: <what should appear or disappear in spans>
   - Side effects to watch: <timeout, runtime, regression>
   ## Falsification
   <which of the above, if observed, would refute the mechanism>
   ```

   `P(regress)` is the load-bearing field. Seed it from the reference-class
   base rate — call `trace_similar` on your planned change and read how many of
   the nearest neighbours regressed — then adjust, and state the adjustment.
   Do not default to optimism: if the base rate says half of similar changes
   regressed, a `P(regress)` near 0 needs an explicit, falsifiable reason. The
   `Train passrate Δ` interval must be consistent with `P(regress)` (you cannot
   claim a tight positive Δ while also claiming a high regression probability).
   This file is provisional until the critic (step 5) has challenged it.

4. **Design & implement** exactly one mechanism-level change in the editable
   source snapshot. One candidate tests one hypothesis — if you are tempted to
   add "and also...", that is a second candidate; drop it.
5. **Adversarial reference-class review (critic subagent) — MANDATORY.**
   Before finalizing, submit the candidate to an adversarial critic. Spawn
   **one** general-purpose subagent whose sole job is to argue, from the
   ledger, that this candidate will regress. Hand it your candidate one-liner,
   mechanism, and the actual diff. Instruct the subagent to:
   a. call `trace_similar(<the diff or a faithful description>, k=8)`;
   b. read each neighbour's `passrate_delta` and `regressed` **directly from
      the `trace_similar` result** — these are the optimizer's authoritative,
      parent-relative numbers. Do **NOT** recompute deltas by comparing
      iterations yourself (e.g. comparing every neighbour to the current best);
      that mis-picks the parent and corrupts the base rate. Use
      `trace_candidate_outcome` only to inspect *how* a regressed neighbour
      failed (its per-task examples), never to re-derive its delta.
   c. compute the **base rate** straight from the `regressed` flags:
      "of the N nearest, X regressed (regressed=true), Y flat, Z advanced →
      P(regress|class) = X/N"; then name the **dominant failure mode of the
      regressed neighbours** (from their `trace_candidate_outcome`);
   d. write `./critique.md` with exactly this shape and return its strongest
      single challenge:

      ```
      # iter_<THIS> critique
      ## Reference class (trace_similar query + k)
      - <sim> iter_<NNN>  passrate_delta=<…> regression_count=<…>
      - … (the k nearest)
      ## Base rate
      - of <N> nearest: <X> regressed / <Y> flat / <Z> advanced  → P(regress|class) ≈ <…>
      ## Dominant failure mode of regressed neighbours
      <one paragraph, grounded in their real per-task outcomes>
      ## Challenge
      <the single strongest, falsifiable reason THIS candidate will regress>
      ## Verdict
      <revise | proceed-with-justification>
      ```

   Then **you must respond** to the challenge: either **revise** the candidate
   to defuse it (return to step 4 and re-run this review — at most 2 critic
   rounds), or keep it and add a `## Critic response` section to
   `./prediction.md` giving a falsifiable reason the dominant failure mode does
   not apply, AND reconcile your `P(regress)` with the critic's base rate. A
   candidate may not proceed if its only answer to the challenge is optimism.
6. **Smoke check.** Run a lightweight syntax/import check on the edited snapshot.
7. **Write `pending_eval.json`** with exactly one candidate.

## Evidence interface

This variant is **ledger-first**. The RunStore MCP servers are registered in
your workspace regardless of run mode — query them before opening raw files,
and fall back to raw `reference_iterations/iter_NNN/` and `traces/` bundles only
to verify a failure mode or pull a concrete excerpt.

The `runstore-tools` MCP server (structured facts, exact-id lookups):
- raw artifact tools — `mcp__runstore-tools__runstore_artifact_list`, `mcp__runstore-tools__runstore_artifact_get`,
  `mcp__runstore-tools__runstore_artifact_search`
- structured fact tools — `mcp__runstore-tools__runstore_fact_state`,
  `mcp__runstore-tools__runstore_fact_candidate_outcome`, `mcp__runstore-tools__runstore_fact_compare_iterations`,
  `mcp__runstore-tools__runstore_fact_task_history`, `mcp__runstore-tools__runstore_fact_trace`,
  `mcp__runstore-tools__runstore_fact_modification`, `mcp__runstore-tools__runstore_fact_proposer_call`,
  `mcp__runstore-tools__runstore_fact_file_history`, `mcp__runstore-tools__runstore_fact_proposal`
- evidence-link tools — `mcp__runstore-tools__runstore_link_for`, `mcp__runstore-tools__runstore_link_explain_iteration`,
  `mcp__runstore-tools__runstore_link_explain_proposal`, `mcp__runstore-tools__runstore_link_chain_task`

The `worldcalib-traces` MCP server (semantic search — the backbone of the
reference-class critic; the SQL `runstore_fact_*` tools only do exact-id lookups):
- `mcp__worldcalib-traces__trace_similar(diff_or_query, k?)` — historical iters whose
  candidate diff is semantically closest to a description or a diff you are considering
  (cosine over embeddings); returns `{iteration, similarity, status_counts}`. This is how
  step 5 builds the reference class and base rate.
- `mcp__worldcalib-traces__trace_candidate_outcome(iteration, candidate_id)` — full per-candidate
  outcome: passrate, modified files, regressed/breakthrough task examples.
- `mcp__worldcalib-traces__trace_compare_iterations(left, right)` — per-task regression/breakthrough
  classification + score delta between two iters (use a neighbour vs its parent to read its real
  `passrate_delta` / `regression_count`).
- `mcp__worldcalib-traces__trace_iteration_metadata`, `mcp__worldcalib-traces__trace_file_history`,
  `mcp__worldcalib-traces__trace_task_history` — iteration passrate/frontier metadata, and per-file /
  per-task history.

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
- **has passed the adversarial critic (step 5):** `./critique.md` exists with a
  populated reference class and base rate, and `./prediction.md` carries a
  `P(regress)` reconciled with that base rate (plus a `## Critic response`
  section if you proceeded over a `revise` verdict). A candidate with no
  `critique.md`, no `P(regress)`, or a `P(regress)` that contradicts its own
  reference class will be rejected.

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
