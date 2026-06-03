---
name: worldcalib-proposer-agentic-base-core
description: Shared NON-calibration proposer contract for agentic agent policies — objective, generalization rules, search space, workflow (no calibration step), evidence interface, hard rules, quality gate, edit scope. Included by every per-task agentic skill (both arms) via INCLUDE; the calib arm layers _calib_addon.md on top. The backend-specific surface is spliced ahead of this fragment.
---

## Objective

Maximize the agent's **episode passrate** (the primary metric) and average
reward on the task's train split, in a way that **transfers** to held-out
episodes of the same task. `passrate` is the fraction of episodes solved. Two
outcome resolutions are available in each candidate's
`candidate_results/<id>.json`: the per-task-type `score_breakdown` (when the
dataset defines task-types), and the per-episode `tasks[]` rows (each carries a
`task_id` + `score`/`passed`). Use whichever the evidence makes most legible to
classify failure modes (see the task-specific tail below).

## Generalization comes first — do not overfit the scored split

The train split is small. A change that only helps a handful of saved episodes
via narrow special-cases is overfitting, not progress. The test for every
change: **would this mechanism help an agent facing many unfamiliar episodes of
the same task?** Do not hardcode answers, specific commands / SQL / tool
arguments, entity names, account ids, or branch on saved episode indices. Use
traces only to classify failure modes as input to a *general* fix, never as a
lookup table.

## Search space

The search space is the agent policy source — arbitrary Python in the editable
surface described above. You may rewrite history handling, tool augmentation,
output repair, control flow, add components, or replace the mechanism wholesale.
Exploitation (refine the current mechanism) and exploration (a structurally
different policy) are both valid.

## Subagents

You can call a general-purpose subagent at any time you find it useful — it is a
tool available to you, optional and at your discretion.

## Workflow

1. **Analyze.** Read evidence (traces, score_breakdown — see *Evidence
   interface* below), deep-read failed *and* successful episodes. Classify
   recurring failure modes (see the task-specific hints below). This is the most
   important step.
2. **Hypothesize.** State one falsifiable hypothesis: a general policy mechanism
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
outcome record — the per-task-type `score_breakdown` and the per-episode
`tasks[]` rows (each with `task_id` + `score`/`passed`) — to learn from.

## Hard rules (read before editing)

1. **No late imports of `worldcalib.*` inside method bodies.** Bind every
   `from worldcalib...import X` at module top level. The optimizer isolates the
   candidate's `sys.modules` only during construction; a late import resolves to
   the host package and breaks with signature errors → every episode fails.
2. **Runtime code MUST NOT `import worldcalib.metrics`** or any scoring helper —
   it is a cheat path and the candidate is hard-rejected before eval.
3. **When an iter failed, read the actual error before hypothesizing.** If every
   episode errored, read `candidate_results/<id>.json` `tasks[0]` (`status` /
   `error`) and your diff to find the broken import/signature. Do not write a
   speculative diagnosis.

## Quality gate

Before writing `pending_eval.json`, verify the candidate **is a real mechanism
change** to the agent policy (not a trivial constant tweak), **does not hardcode**
task-specific answers / ids / tool arguments, and **would plausibly help
unfamiliar episodes** of the same task.

## Edit scope

Work inside the copied source snapshot. The editable policy is the
`seed_passthrough.py` named in the surface above (and the backend `base.py` if a
mechanism genuinely needs a shared helper). Do not modify the outer optimizer,
evaluator, data loaders, or run artifacts.
