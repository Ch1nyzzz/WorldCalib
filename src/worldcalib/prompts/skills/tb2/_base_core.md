---
name: worldcalib-proposer-tb2-base-core
description: Shared non-calibration proposer contract for the Terminal-Bench 2.0 harness. Included by both arms; the calibrated arm layers shared/_calib_addon.md on top.
---

## Objective

Maximize `average_score` — Terminal-Bench's published metric — in a way that
**transfers** to unseen tasks. A task's verifier is pass/fail: its reward is 1
when every test passes and 0 otherwise. Each task is run `k` times and its score
is the **mean** of those trials, so with `k=2` a task scores 0, 0.5 or 1; the
candidate's `average_score` is the mean of the per-task scores. `passrate` on the
score table carries this same number. `token_consuming`, tool-call count, and
wall-clock are reported diagnostics, not objectives. Predict cost impact, but do
not trade away score to shrink it. The per-task breakdown is in each candidate's
`candidate_results/<id>.json` under `score_breakdown`.

## Generalization comes first — do not overfit the scored split

The scored split is tiny and is *not* the population you are optimizing for. The
objective is the harness's behavior on unseen tasks; a higher train
`average_score` is only a proxy, and a change can raise it while degrading the
harness broadly. You cannot tell the difference from the train score, so:

- Do not hardcode or branch on task ids, instruction text, reference solutions,
  or scorer shortcuts.
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

## Choosing your parent (self-select)

The harness materialises the current best-scoring candidate into your editable
source as the DEFAULT parent, but the choice is yours:

- BEFORE the Analyze step, read `frontier_manifest.json` (every prior
  candidate's score / hypothesis / parent edge / snapshot path) and
  `task_score_matrix.json` (the full iteration x task score history).
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

Begin with whichever cumulative summary files are present under `summaries/` —
`evolution_summary.jsonl` (the full event history) and `best_candidates.json`
(the current quality frontier). If no `summaries/` directory is provided this
run, work directly from the raw `reference_iterations/iter_NNN/` bundles instead.
Either way, inspect raw `reference_iterations/iter_NNN/` bundles and `traces/`
files selectively to validate the failure mode and the source change. Do not
infer a mechanism from summaries alone.

## Hard rules (read before editing)

1. **When an iter regressed, read the actual trajectory before hypothesizing.**
   If a candidate scored 0 on tasks, read `candidate_results/<id>.json` and the
   trajectory/diff to find the broken command, prompt, or config. Do not write a
   speculative diagnosis.
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
  task ids, instruction text, reference solutions, or scorer shortcuts; candidate
  runtime code must not call the verifier.
- **would plausibly help an agent facing many unfamiliar tasks** — not just the
  saved split. A change whose benefit is a handful of saved tasks, or a stack of
  narrow per-domain special cases, is overfitting and will be rejected even if
  train `average_score` rises.
- **uses the isolated source snapshot** for source edits.

## Edit scope

Work inside the copied terminus-2 harness snapshot the iteration message names
(plus the optional generated wrapper directory); the iteration message lists the
exact editable paths. Do not modify the Terminal-Bench tasks (`instruction.md`,
`environment/`, `solution/`, `tests/`, `task.toml`), the verifier, the harbor
runner, the outer optimizer, or run artifacts as part of a candidate.
