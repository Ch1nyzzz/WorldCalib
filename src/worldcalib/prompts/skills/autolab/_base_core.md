---
name: worldcalib-proposer-autolab-base-core
description: Shared NON-calibration proposer contract for the AutoLab terminus-2 harness agent — objective (continuous reward), generalization rules, search space, workflow (no calibration step), evidence interface (default + organized MODE blocks), quality gate, edit scope. Included by both the autolab_calib and autolab_nowmc arms via INCLUDE; the calib arm layers _calib_addon.md on top. The AutoLab-specific surface is spliced ahead of this fragment.
---

## Objective

Maximize `average_score` — the mean **continuous reward** the harness earns
across the AutoLab tasks — in a way that **transfers** to unseen tasks. Reward is
in [0, 1] with 0.5 anchored to a human reference solution; `passrate` (the
fraction of tasks at or above the reward gate) is reported alongside it as a
coarse companion, and `token_consuming`, tool-call count, and wall-clock are
reported diagnostics, not objectives. Predict cost impact, but do not trade away
reward to shrink it. The per-task breakdown is in each candidate's
`candidate_results/<id>.json` under `score_breakdown`.

## Generalization comes first — do not overfit the scored split

The scored split is tiny and is *not* the population you are optimizing for. The
objective is the harness's behavior on unseen tasks; a higher train
`average_score` is only a proxy, and a change can raise it while degrading the
harness broadly. You cannot tell the difference from the train score, so:

- Do not hardcode or branch on task ids, domains, instruction text, the metric
  name/direction, reference solutions, or scorer shortcuts.
- Tie each change to a failure mode you actually observed in the evidence — not
  to a speculation and not to a kind of change that "sounds useful."
- Before submitting, name a class of currently-strong tasks the change could
  regress, and argue why it won't. If you can't, the change is not ready.

## Search space

The search space is the candidate source itself — the whole agent in the editable
surface described above: the `BaseAgent` implementation in `terminus_2/`, which
you may keep, modify, or replace wholesale (only the `BaseAgent` interface is
fixed). That includes its control loop, what state persists across steps/attempts,
how/when it verifies/retries/finalizes, its prompts, and any `agent_kwargs`.
Exploitation (refining the current mechanism) and exploration (a structurally
different agent) are both valid moves. Do not bias toward small edits and do not
bias toward large ones — choose the change that best targets a real failure mode.
A genuinely new mechanism — a different control-loop topology, what is remembered
across attempts, a verification/retry scheme, or information-flow structure — is a
first-class candidate, not a last resort.

## Subagents

You can call a general-purpose subagent at any time you find it useful — it is a
tool available to you, optional and at your discretion. The per-trajectory
failure analysis (deep-reading many task trajectories) is a natural thing to
delegate.

## Workflow

1. **Analyze.** Read the available evidence (see *Evidence interface* below) and
   deep-read trajectories for recent iterations — both tasks the harness scored
   well and tasks it scored poorly. Classify the recurring harness failure modes
   you actually observe in the traces — derive them from the evidence, do not
   pattern-match to a list. This is the most important step.
2. **Hypothesize.** State one falsifiable hypothesis: a mechanism-level change to
   the harness, tied to a failure mode you classified, with a first-principles
   argument for why it improves the agent's behavior on unseen tasks (not merely
   on the scored split).
3. **Design & implement** exactly one mechanism-level change in the editable
   harness snapshot. One candidate tests one hypothesis — if you are tempted to
   add "and also...", that is a second candidate; drop it.
4. **Smoke check.** Run a lightweight syntax/import check on the edited snapshot.
5. **Write `pending_eval.json`** with exactly one candidate (see the conventions
   in the surface above).

Reason across iterations, not just within one. The evidence available to you is
the full history of this run — every prior candidate, its diff, and its outcome,
*including which tasks each change improved and which it regressed*. Query that
history (see *Evidence interface*) before proposing, so your change builds on
what is already known rather than re-deriving a past result or repeating a past
failure.

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
  - `runstore_fact_candidate_outcome` — a candidate's average_score and per-task scores.
  - `runstore_fact_compare_iterations` — score and candidate differences between two iterations.
  - `runstore_fact_modification` — the source diff a candidate made.
  - `runstore_fact_trace` — one task's trajectory summary for a candidate.
  - `runstore_fact_task_history` — how one task's score evolved across iterations.
  - `runstore_fact_file_history` — how one source file changed across candidates.
  - `runstore_fact_proposal` / `runstore_fact_proposer_call` — a candidate's recorded
    hypothesis and changes / the proposer session that produced it.
  - `runstore_fact_state` — current run-state snapshot.
- link (provenance) tools:
  - `runstore_link_explain_proposal` — a candidate's chain: its outcome plus the tasks
    it improved (breakthrough) and the tasks it regressed (regression).
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

1. **When an iter regressed, read the actual trajectory before hypothesizing.**
   If a candidate scored 0 (or far below the gate) on tasks, read
   `candidate_results/<id>.json` and the trajectory/diff to find the broken
   command, prompt, or config. Do not write a speculative diagnosis.
2. **Runtime harness code must not call the verifier or read held-out
   references.** It must not inspect any task's `solution/`, `tests/`, `task.toml`,
   or the scorer's `reward.json` / `results.json` at inference time — these are
   cheat paths and the candidate is hard-rejected.
3. **Keep the candidate loadable** through the source-backed harness recorded in
   `pending_eval.json` — a syntax/import break makes every task fail.

## Quality gate

Before writing `pending_eval.json`, verify the candidate:

- **is a real mechanism change**, not just a retry-count / timeout / context-
  budget / prompt-length / agent-kwarg variant. Parameter and agent-kwarg changes
  are allowed only as supporting detail of a mechanism change; a candidate whose
  substantive change is only a parameter will be rejected.
- **does not inspect held-out references at inference time** and does not hardcode
  task ids, domains, instruction text, the metric name/direction, reference
  solutions, or scorer shortcuts; candidate runtime code must not call the
  verifier.
- **would plausibly help an agent facing many unfamiliar tasks** — not just the
  saved split. A change whose benefit is a handful of saved tasks, or a stack of
  narrow per-domain special cases, is overfitting and will be rejected even if
  train `average_score` rises.
- **uses the isolated source snapshot** for source edits.

## Edit scope

Work inside the copied terminus-2 harness snapshot the iteration message names
(plus the optional generated wrapper directory); the iteration message lists the
exact editable paths. Do not modify the AutoLab tasks (`instruction.md`,
`environment/`, `solution/`, `tests/`, `task.toml`), the verifier, the harbor
runner, the outer optimizer, or run artifacts as part of a candidate.
