---
name: worldcalib-proposer-memory-calib-addon
description: Calibration layer (self-distill world-model calibration, NO external critic) layered ONTO the base memory proposer contract — the append-only world_model_calibration.md protocol, prev_prediction.md, the per-task pass↔fail prediction.md template (predict concrete per-task_id question flips, NOT score/passrate deltas), and the per-task self-grade distill block. Included by every per-benchmark memory calib skill immediately after memory/_base_core.md.
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

**Predicting per question is not overfitting.** Memory tasks are QUESTIONS; you
will name the specific question `task_id`s your change should flip pass↔fail.
That is a *calibration judgement about a general mechanism* — which questions a
general change is likely to flip — and is distinct from overfitting: the runtime
policy must never branch on a question's `task_id` or embed its answer. The
prediction may name questions; the code may not.

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade. **Before the
base `Design & implement` step**, write `prediction.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. `cat ./runtime_config.md` for the ground-truth target model/base_url — do NOT
   infer model family from `src/worldcalib/model.py` defaults (they are
   launcher-overridden).
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it, then read the previous
   iter's **real per-task** outcome from `candidate_results/<id>.json` — the
   `tasks[]` rows (each question's `task_id` + `score`/`passed`) — compared
   against the **base iter's** `tasks[]`, plus the trace evidence. **Self-grade
   per task**: for each `task_id` you predicted to flip (fail→pass or pass→fail),
   did it actually flip? Which questions flipped **pass→fail that you did NOT
   name** (blind spots)? Did any question you called **`model-limited` flip to
   pass**? For each wrong call, what does the trace say went differently? Then
   append:

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

Predict at the **question level**: name the specific questions your change flips
and tie each to that question's trace evidence.

```
# iter_<THIS> prediction
## Candidate (one line)
## Base — the prior iter you rebuilt on (exact, e.g. iter_4, or `clean` for the seed)
## Why this change & why it optimizes the whole system
<the policy edit, the failure mode it attacks, and why the mechanism generalizes to unfamiliar questions — a general mechanism, not a per-question hardcode>
## Mechanism — the behavioral change, and the failure mode (from the traces) it attacks
## Per-task effects — the falsifiable prediction
# List ONLY questions you expect to CHANGE (a pass↔fail flip), plus any at-risk
# question you are deliberately protecting. One line per question, tied to that
# question's trace.
- <task_id>: fail→pass — <the specific failure in this question's trace the mechanism fixes>
- <task_id>: pass→fail — <why this question is now at risk>
- <task_id>: pass→pass (protected) — <why this at-risk question stays safe>   [optional]
## Model-limited (questions no harness change can solve)
# Where the trace shows the model itself lacks the reasoning/knowledge — mark it
# here rather than listing it as fail→pass.
- <task_id>: model-limited — <the capability the trace shows the model lacks>
## Falsification
<which named per-task flips, if they do NOT happen, refute the mechanism>
```

Ground each flip in that question's trace, and read the `task_id`s from the prior
`candidate_results/<id>.json` `tasks[]`. The prediction names questions; the
**code stays general** — never branch on a `task_id` or embed an answer. Next
iter you self-grade these flips against the real per-task outcome.
