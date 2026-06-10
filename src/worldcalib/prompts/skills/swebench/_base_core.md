---
name: worldcalib-proposer-swebench-base-core
description: Shared NON-calibration proposer contract for the SWE-bench coding agent — objective, generalization rules, search space, workflow (no calibration step), evidence interface (default + organized MODE blocks), quality gate, edit scope. Included by both the swebench_calib and swebench_nowmc arms via INCLUDE; the calib arm layers _calib_addon.md on top. The SWE-bench-specific surface is spliced ahead of this fragment.
---

## Objective

Maximize `passrate` — the fraction of SWE-bench issues the agent resolves — in a
way that **transfers** to unseen issues. `average_score` is reported alongside it
and tracks partial progress; `token_consuming`, tool-call count, and wall-clock
are reported diagnostics, not objectives. Predict cost impact, but do not trade
away resolution reliability to shrink it. The per-issue breakdown is in each
candidate's `candidate_results/<id>.json` under `score_breakdown`.

## Generalization comes first — do not overfit the scored split

The scored split is tiny and is *not* the population you are optimizing for. The
objective is the agent's behavior on unseen issues; a higher train `passrate` is
only a proxy, and a change can raise it while degrading the agent broadly. You
cannot tell the difference from the train score, so:

- Do not hardcode or branch on task/issue/repo/file ids, gold patches, test
  patches, or scorer shortcuts.
- Tie each change to a failure mode you actually observed in the evidence — not
  to a speculation and not to a kind of change that "sounds useful."
- Before submitting, name a class of currently-passing issues the change could
  break, and argue why it won't. If you can't, the change is not ready.

## Search space

The search space is the candidate source itself — arbitrary Python in the
editable surface described above. Exploitation (refining the current mechanism)
and exploration (a structurally different mechanism) are both valid moves. Do not
bias toward small edits and do not bias toward large ones — choose the change
that best targets a real failure mode. A genuinely new mechanism — a different
control-loop topology, context strategy, verification step, or information-flow
structure — is a first-class candidate, not a last resort.

## Subagents

You can call a general-purpose subagent at any time you find it useful — it is a
tool available to you, optional and at your discretion. The per-trajectory
failure analysis (deep-reading many task trajectories) is a natural thing to
delegate.

## Choosing your parent (self-select)

The harness materialises the current lex-best candidate (passrate first,
average_score tiebreak) into your editable source as the DEFAULT parent, but
the choice is yours:

- BEFORE the Analyze step, read `frontier_manifest.json` (every prior
  candidate's passrate / average_score / hypothesis / parent edge / snapshot
  path) and `task_score_matrix.json` (the full iteration x task score
  history).
- Judge per-task variance from the matrix history. A one-off high on a noisy
  task is not a frontier — do not chase it; a mechanism that repeats across
  iterations is.
- You may keep the default parent, wholesale-copy any
  `reference_iterations/iter_NNN/source_snapshot/` over your editable source,
  or graft mechanisms from several prior iterations.
- Declare the parent you actually built on in the candidate config as
  `"base_iter": <N>` (`0` = clean seed). If you replaced the default or
  grafted, say so in one line of the hypothesis.

## Workflow

1. **Analyze.** Read the available evidence (see *Evidence interface* below) and
   deep-read both failed *and* successful trajectories for recent iterations.
   Classify the recurring agent failure modes you actually observe in the traces
   — derive them from the evidence, do not pattern-match to a list. This is the
   most important step.
2. **Hypothesize.** State one falsifiable hypothesis: a mechanism-level change,
   tied to a failure mode you classified, with a first-principles argument for why
   it improves the agent's decisions on unseen issues (not merely on the scored
   split).
3. **Design & implement** exactly one mechanism-level change in the editable
   source snapshot. One candidate tests one hypothesis — if you are tempted to add
   "and also...", that is a second candidate; drop it.
4. **Smoke check.** Run a lightweight syntax/import check on the edited snapshot.
5. **Write `pending_eval.json`** with exactly one candidate (see the conventions
   in the surface above).

Reason across iterations, not just within one. The evidence available to you is
the full history of this run — every prior candidate, its diff, and its outcome,
*including which tasks each change fixed and which it broke*. Query that history
(see *Evidence interface*) before proposing, so your change builds on what is
already known rather than re-deriving a past result or repeating a past failure.

## Evidence interface

<!-- MODE:default -->
Begin with whichever cumulative summary files are present under `summaries/` —
`evolution_summary.jsonl` (the full event history) and `best_candidates.json`
(the current quality frontier). If no `summaries/` directory is provided this
run, work directly from the raw `reference_iterations/iter_NNN/` bundles instead.
Either way, inspect raw `reference_iterations/iter_NNN/` bundles and `traces/`
files selectively to validate the failure mode and the source change. Do not
infer a mechanism from summaries alone.
<!-- END MODE:default -->
<!-- MODE:organized -->
Read `state.md` first for orientation — it is a current state snapshot only, not
evidence, not diagnosis, not a plan. Then use the `runstore-tools` MCP server to
inspect candidate outcomes, iteration comparisons, task histories, traces, and
modifications before opening raw files. Use the tool results to decide which raw
`reference_iterations/` and `traces/` files to read for verification and concrete
excerpts. Cumulative summary files are not provided in this mode.

The `runstore-tools` MCP server exposes the following (every name is prefixed
`mcp__runstore-tools__`). Query these before opening raw files:
- artifact tools — `runstore_artifact_list` / `_get` / `_search`: list, fetch, or
  search the raw stored artifacts.
- fact tools:
  - `runstore_fact_candidate_outcome` — a candidate's passrate and per-task scores.
  - `runstore_fact_compare_iterations` — score and candidate differences between two iterations.
  - `runstore_fact_modification` — the source diff a candidate made.
  - `runstore_fact_trace` — one task's trajectory summary for a candidate.
  - `runstore_fact_task_history` — how one task's pass/fail evolved across iterations.
  - `runstore_fact_file_history` — how one source file changed across candidates.
  - `runstore_fact_proposal` / `runstore_fact_proposer_call` — a candidate's recorded
    hypothesis and changes / the proposer session that produced it.
  - `runstore_fact_state` — current run-state snapshot.
- link (provenance) tools:
  - `runstore_link_explain_proposal` — a candidate's chain: its outcome plus the tasks
    it fixed (breakthrough) and the tasks it broke (regression).
  - `runstore_link_explain_iteration` — one iteration consolidated: proposer call +
    modification + outcome + links.
  - `runstore_link_chain_task` — one task across iterations: eval results → traces →
    the modifications that produced them.
  - `runstore_link_for` — raw evidence-graph links filtered by source/target/relation.

The `worldcalib-traces` MCP server adds semantic search over historical iter
diffs (the SQL `runstore_fact_*` tools only support exact-id lookups):
- `mcp__worldcalib-traces__trace_similar(diff_or_query, k?)` — find past iters
  whose candidate diff is semantically closest to a natural-language description
  or a candidate diff you are considering. Useful to avoid re-trying mechanisms
  that already failed and to surface non-obvious prior attempts.
<!-- END MODE:organized -->
<!-- MODE:organized-no-state -->
Use the `runstore-tools` MCP server first to inspect candidate outcomes,
iteration comparisons, task histories, traces, and modifications before opening
raw files. This organized run intentionally does not provide `state.md`; do not
look for it. Use the tool results to decide which raw `reference_iterations/` and
`traces/` files to read for verification and concrete excerpts. Cumulative
summary files are not provided in this mode. The `runstore-tools` and
`worldcalib-traces` MCP servers expose the same tools described in the organized
mode above.
<!-- END MODE:organized-no-state -->
<!-- MODE:organized-summaries -->
Read `state.md` first for orientation — a current state snapshot only. Then use
the `runstore-tools` MCP server to inspect candidate outcomes, iteration
comparisons, task histories, traces, and modifications before opening raw files.
Cumulative summary files are also available in this ablation; treat them only as
orientation — evidence claims should be grounded in RunStore tool results or raw
trace/reference excerpts. The `runstore-tools` and `worldcalib-traces` MCP
servers expose the same tools described in the organized mode above.
<!-- END MODE:organized-summaries -->

## Hard rules (read before editing)

1. **When an iter failed, read the actual error before hypothesizing.** If a
   candidate's tasks errored out (not just failed tests), read
   `candidate_results/<id>.json` and the trajectory/diff to find the broken
   command, import, or signature. Do not write a speculative diagnosis.
2. **Runtime candidate code must not call the evaluator or read held-out
   solutions.** It must not inspect gold patches, test patches, or scorer
   internals at inference time — these are cheat paths and the candidate is
   hard-rejected.
3. **Keep the candidate loadable** through the source-backed scaffold recorded in
   `pending_eval.json` — a syntax/import break makes every task fail.

## Quality gate

Before writing `pending_eval.json`, verify the candidate:

- **is a real mechanism change**, not just a retry-count / timeout / context-
  budget / prompt-length variant. Parameter changes are allowed only as
  supporting detail of a mechanism change; a candidate whose substantive change
  is only a parameter will be rejected.
- **does not inspect held-out solutions at inference time** and does not hardcode
  repository/issue/file/task ids, gold patches, test patches, or scorer
  shortcuts; candidate runtime code must not call the evaluator.
- **would plausibly help an agent facing many unfamiliar issues** — not just the
  saved split. A change whose benefit is a handful of saved issues, or a stack of
  narrow per-pattern special cases, is overfitting and will be rejected even if
  train `passrate` rises.
- **uses the isolated source snapshot** for source edits.

## Edit scope

Work inside the copied mini-SWE-agent source snapshot under
`candidate/upstream_source/mini-swe-agent/**` and the optional generated wrapper
directory; the iteration message lists the exact editable paths. Do not modify
the SWE-bench scorer, gold patches, test patches, dataset files, the outer
optimizer, or run artifacts as part of a candidate.
