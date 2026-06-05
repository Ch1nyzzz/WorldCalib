---
name: worldcalib-proposer-reasoning-calib-addon
description: Calibration layer (self-distill world-model calibration, NO external critic) layered ONTO the base reasoning proposer contract — the append-only world_model_calibration.md protocol, prev_prediction.md, the per-task pass↔fail prediction.md template (predict concrete per-task_id flips, NOT score/passrate deltas), and the per-task self-grade distill block. Included by the reasoning_calib arm immediately after _base_core.md.
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
- **Per iter, your bet: `./prediction.md`** (written BEFORE editing source).

**Predicting per puzzle is not overfitting.** You will name specific puzzle
`task_id`s your change should solve or break. That is a *calibration judgement
about a general mechanism* — which puzzles a general change is likely to flip —
and is distinct from overfitting: the runtime solver must never branch on a saved
task id / index or embed a puzzle's answer. The prediction may name puzzles; the
code may not.

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade. **Before the
base `Design & implement` step**, write `prediction.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. `cat ./runtime_config.md` for the ground-truth target model/base_url.
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it, then read the previous
   iter's **real per-task** outcome from `candidate_results/<id>.json` — the
   `tasks[]` rows (each puzzle's `task_id` + `score`/`passed`) — compared against
   the **base iter's** `tasks[]`, plus the trace evidence. **Self-grade per
   task**: for each `task_id` you predicted to flip (fail→pass or pass→fail), did
   it actually flip? Which puzzles flipped **pass→fail that you did NOT name**
   (blind spots)? Did any puzzle you called **`model-limited` flip to pass**? For
   each wrong call, what does the trace say went differently? Then append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Per-task check (self): predicted flips hit X/Y — called right: <task_ids>; called wrong: <task_ids>
   - Blind-spot regressions: <task_ids that flipped pass→fail and were NOT predicted>
   - Model-limited overruled: <task_ids called model-limited that nonetheless flipped to pass — these were solvable after all>
   - Why mispredicted: <for each wrong call, the trace reason the real outcome differed>
   - Belief update: <one sentence revising the world model so the next per-task prediction is better>
   ```

   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the append
   — start cold.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest.

### Before Design — write the self-graded bet `./prediction.md`

Predict at the **puzzle level**: name the specific puzzles your change flips and
tie each to that puzzle's trace evidence.

```
# iter_<THIS> prediction
## Candidate (one line)
## Base — the prior iter you rebuilt on (exact, e.g. iter_4, or `clean` for the seed)
## Why this change & why it optimizes the whole system
<the policy edit, the failure mode it attacks, and why the mechanism generalizes to unfamiliar puzzles — a general mechanism, not a per-puzzle hardcode>
## Mechanism — the behavioral change, and the failure mode (from the traces) it attacks
## Per-task effects — the falsifiable prediction
# List ONLY puzzles you expect to CHANGE (a pass↔fail flip), plus any at-risk
# puzzle you are deliberately protecting. One line per task, tied to its trace.
- <task_id>: fail→pass — <the specific failure in this puzzle's trace the mechanism fixes>
- <task_id>: pass→fail — <why this puzzle is now at risk>
- <task_id>: pass→pass (protected) — <why this at-risk puzzle stays safe>   [optional]
## Model-limited (puzzles no harness change can solve)
# Where the trace shows the model itself lacks the reasoning — mark it here
# rather than listing it as fail→pass.
- <task_id>: model-limited — <the reasoning capability the trace shows the model lacks>
## Falsification
<which named per-task flips, if they do NOT happen, refute the mechanism>
```

Ground each flip in that puzzle's trace, and read the `task_id`s from the prior
`candidate_results/<id>.json` `tasks[]`. The prediction names puzzles; the **code
stays general** — never branch on a `task_id` or embed an answer. Next iter you
self-grade these flips against the real per-task outcome.
