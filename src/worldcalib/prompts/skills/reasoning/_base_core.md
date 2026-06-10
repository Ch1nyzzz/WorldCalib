---
name: worldcalib-proposer-reasoning-base-core
description: Shared NON-calibration proposer contract for the ARC-AGI-2 reasoning solver — objective, generalization rules, search space, workflow (no calibration step), evidence interface, hard rules, quality gate, edit scope. Included by both the reasoning_calib and reasoning_nowmc arms via INCLUDE; the calib arm layers _calib_addon.md on top. The ARC-specific surface is spliced ahead of this fragment.
---

## Objective

Maximize the solver's **task passrate** (the primary metric) and average score on
the task's train split, in a way that **transfers** to held-out ARC-AGI-2 tasks.
`passrate` is the fraction of tasks fully solved (every test grid matched within
the pass@2 budget); the continuous `average_score` credits partial solves (the
fraction of a task's test grids matched). The per-category (task-type) breakdown
is in each candidate's `candidate_results/<id>.json` under `score_breakdown`.

## Generalization comes first — do not overfit the scored split

The train split is small. A change that only helps a handful of saved tasks via
narrow special-cases is overfitting, not progress. The test for every change:
**would this mechanism help a solver facing many unfamiliar ARC tasks?** Do not
hardcode answers, specific grids, transformation rules keyed to particular tasks,
color palettes, grid dimensions, or branch on saved task ids / indices. Use
traces only to classify failure modes as input to a *general* fix, never as a
lookup table.

## Search space

The search space is the solver policy source — arbitrary Python in the editable
surface described above. You may rewrite prompt construction, grid rendering,
parsing/repair, the attempt budget, the control flow of `solve_task`, add
components, or replace the mechanism wholesale. Exploitation (refine the current
mechanism) and exploration (a structurally different solving strategy) are both
valid.

## Subagents

You can call a general-purpose subagent at any time you find it useful — it is a
tool available to you, optional and at your discretion.

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

1. **Analyze.** Read evidence (traces, score_breakdown — see *Evidence
   interface* below), deep-read failed *and* solved tasks. Classify recurring
   failure modes (see the task-specific hints below). This is the most important
   step.
2. **Hypothesize.** State one falsifiable hypothesis: a general solver mechanism
   tied to a failure mode you classified.
3. **Design & implement** exactly one mechanism-level change in the editable
   snapshot (the `seed_passthrough.py` named in the surface above). One candidate
   tests one hypothesis.
4. **Smoke check.** Run a lightweight syntax/import check on the edited snapshot.
5. **Write `pending_eval.json`** with exactly one candidate (see the conventions
   in the surface above).

## Evidence interface

Inspect the raw evidence directly: the `reference_iterations/iter_NNN/` bundles
(each with `candidate_results` and a `diff`) and the `traces/` files validate the
failure mode and the change, and `candidate_results/<id>.json` carries the
outcome record — the per-task-type `score_breakdown` — to learn from.

## Hard rules (read before editing)

1. **No late imports of `worldcalib.*` inside method bodies.** Bind every
   `from worldcalib...import X` at module top level. The optimizer isolates the
   candidate's `sys.modules` only during construction; a late import resolves to
   the host package and breaks with signature errors → every task fails.
2. **Runtime code MUST NOT `import worldcalib.metrics`** (or the evaluation /
   scoring helpers, or reopen the task json to read gold test outputs) — these
   are cheat paths and the candidate is hard-rejected before eval.
3. **When an iter failed, read the actual error before hypothesizing.** If every
   task errored, read `candidate_results/<id>.json` `tasks[0]` (`status` /
   `error`) and your diff to find the broken import/signature. Do not write a
   speculative diagnosis.

## Quality gate

Before writing `pending_eval.json`, verify the candidate **is a real mechanism
change** to the solver (not a trivial constant tweak), **does not hardcode**
task-specific answers / grids / rules, **does not peek at test outputs or import
scoring code**, and **would plausibly help unfamiliar ARC tasks**.

## Edit scope

Work inside the copied source snapshot. The editable solver is the
`seed_passthrough.py` named in the surface above (and `arc_scaffolds/base.py` if
a mechanism genuinely needs a shared helper). Do not modify the outer optimizer,
the evaluation runner, the data loader, the scoring, or run artifacts.
