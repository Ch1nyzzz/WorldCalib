---
name: worldcalib-proposer-autolab-calib-addon
description: Calibration layer (self-distill world-model calibration, NO external critic) layered ONTO the base AutoLab proposer contract — the append-only world_model_calibration.md protocol, prev_prediction.md, and the per-task pass↔fail prediction.md template (predict concrete per-task_id flips with a per-task reason, NOT reward/score deltas), plus the per-task self-grade distill block. Included by the autolab_calib arm immediately after _base_core.md.
---

## Self-distill calibration protocol (WorldCalib — NO external critic)

This is the calibration layer, applied **in addition to** the base Workflow.
This run uses **self-distill** world-model calibration: there is **no external
critic** — you grade your own prediction. One append-only file per run, one
prediction per iter.

- **Per run, append-only: `./world_model_calibration.md`** (staged into your
  cwd; promoted back automatically). Seeded at iter 0 with an Observability
  template. Every iter ≥ 1 MUST append exactly one new
  `## iter_PREV -> iter_THIS distill` section. Never rewrite prior sections.
- **Previous iter's prediction: `./prev_prediction.md`** (staged if it exists).
  Your prior bet. There is **no** `critic_feedback.md` — you compare it yourself
  against the real outcome.
- **Per iter, your bet: `./prediction.md`** (written BEFORE editing the harness).

**Predict per task — a pass↔fail flip plus a reason — never a score.** AutoLab
has no dataset task-type: the per-task `tasks[]` rows in
`candidate_results/<id>.json` (each carrying `task_id` + the continuous `score`
and the gate-derived `passed`) are the outcome granularity. A task **passes**
when its reward reaches the gate (`score >= gate`); a **flip** is a task crossing
that gate (`fail→pass` or `pass→fail`). Predict **flips**, not reward magnitudes
— do **not** write `~+0.2`-style numbers or an `average_score` delta; those bets
are near-random and drive the optimizer's curse. For **each** task you name, write
a one-line **reason** tied to that task's trace. Naming task_ids is a
*calibration judgement about a general mechanism* — which tasks a general harness
change is likely to flip — and is distinct from overfitting: the runtime harness
must never branch on a `task_id` / domain / instruction or read a task's
reference. **The prediction may name task_ids; the harness code may not.**

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade. **Before the
base `Design & implement` step**, write `prediction.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. Establish the ground-truth target solver model + base_url from the iteration
   message (and `./runtime_config.md` if it is staged).
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it, then read the previous
   iter's **real per-task** outcome from `candidate_results/<id>.json` — the
   `tasks[]` rows (each task's `task_id` + `score`/`passed`) — compared against
   the **base iter's** `tasks[]`, plus the trace evidence. **Self-grade per
   task**: for each `task_id` you predicted to flip (fail→pass or pass→fail), did
   it actually flip? Which tasks flipped **pass→fail that you did NOT name**
   (blind spots)? Did any task you called **`model-limited` flip to pass**? For
   each wrong call, what does the trace say went differently? Then append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Per-task check (self): predicted flips hit X/Y — called right: <task_ids>; called wrong: <task_ids>
   - Blind-spot regressions: <task_ids that flipped pass→fail and were NOT predicted>
   - Model-limited overruled: <task_ids called model-limited that nonetheless flipped to pass — these were reachable after all>
   - Why mispredicted: <for each wrong call, the trace reason the real outcome differed>
   - Belief update: <one sentence revising the world model so the next per-task prediction is better>
   ```

   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the append
   — start cold.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest.

### Before Design — write the self-graded bet `./prediction.md`

Predict at the **task level**: name the specific tasks your harness change flips
and tie **each** to that task's trace evidence with a one-line reason.

```
# iter_<THIS> prediction
## Candidate (one line)
## Base — the prior iter you rebuilt on (exact, e.g. iter_4, or `clean` for the seed)
## Why this change & why it optimizes the whole system
<the harness edit (terminus-2 agent kwargs / config), the failure mode it attacks, and why the mechanism generalizes to unfamiliar tasks — a general mechanism, not a per-task hardcode>
## Mechanism — the behavioral change, and the failure mode (from the traces) it attacks
## Per-task effects — the falsifiable prediction
# List ONLY tasks you expect to CHANGE (a pass↔fail flip at the gate), plus any
# at-risk task you are deliberately protecting. One line per task, each with a
# REASON tied to that task's trace. No score numbers.
- <task_id>: fail→pass — <the specific failure in this task's trace the mechanism fixes>
- <task_id>: pass→fail — <why this task is now at risk under the change>
- <task_id>: pass→pass (protected) — <why this at-risk task stays safe>   [optional]
## Model-limited (tasks no harness change can flip)
# Where the trace shows the model itself cannot reach the gate — mark it here
# rather than listing it as fail→pass.
- <task_id>: model-limited — <the capability the trace shows the model lacks>
## Falsification
<which named per-task flips, if they do NOT happen, refute the mechanism>
```

Ground each flip in that task's trace, and read the `task_id`s and current
`passed` state from the prior `candidate_results/<id>.json` `tasks[]`. The
prediction names tasks; the **harness code stays general** — never branch on a
`task_id` / domain or read a reference. Next iter you self-grade these flips
against the real per-task outcome.
