---
name: worldcalib-proposer-memory-calib-addon
description: Calibration layer (self-distill world-model calibration, NO external critic) layered ONTO the base memory proposer contract — the append-only world_model_calibration.md protocol, prev_prediction.md, the two-sided Upside/Downside prediction.md template, the per-question_type granularity rule, and the self-grade distill block. Included by every per-benchmark memory calib skill immediately after memory/_base_core.md.
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

**Predicting per question_type is not overfitting.** Naming which question
categories a change should improve or regress is a *calibration judgement about a
general mechanism* — which categories a general change is likely to flip — and is
distinct from overfitting: the runtime policy must never branch on an episode
index or embed an episode's answer. The prediction may name categories (and, for
benchmarks with no task-type axis, specific episode `task_id`s); the code may
not.

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade. **Before the
base `Design & implement` step**, write `prediction.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. `cat ./runtime_config.md` for the ground-truth target model/base_url — do NOT
   infer model family from `src/worldcalib/model.py` defaults (they are
   launcher-overridden).
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it, then read the previous
   iter's **real** outcome from `candidate_results/<id>.json` — the
   `score_breakdown` (per `question_type`), or the per-episode `tasks[]`
   `score`/`passed` rows when the tail defines no task-type axis — plus the trace
   evidence. **Self-grade**: for each category (`question_type` *or* episode
   `task_id`) you listed under Upside, did it improve (Δ > +0.02, or a fail→pass
   flip)? For each Downside, did it regress (Δ < −0.02, or a pass→fail flip)?
   Which categories/episodes regressed that you did NOT name (blind spots)? Was
   your Net-bet direction right? Then append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Prediction check (self): Upside hit X/Y; Downside named Z, regressed W; blind-spot regressions: <categories>
   - Outcome mismatch: <which predicted per-category direction diverged; cite the score_breakdown numbers>
   - Unresolved: <what this iter's evidence could not tell us>
   - Belief update: <one sentence revising the world model so the next prediction is better>
   ```

   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the append
   — start cold.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest.

### Before Design — write the self-graded bet `./prediction.md`

```
# iter_<THIS> prediction
## Candidate (one line)
## Base — the prior iter you rebuilt on (exact, e.g. iter_4, or `clean` for the seed)
## Mechanism (why it should move the metric)
## Upside — categories this should IMPROVE (and why)
- <category>: <why>
## Downside — categories that might REGRESS (and why)
- <category>: <why>  (an empty Downside is a red flag)
## Net bet
- Overall train passrate Δ: [low, high]
- Why upside > downside
## Falsification
<which predicted gain/regression, if absent, refutes the mechanism>
```

A **category** is whatever resolution the benchmark tail below specifies:

- **question_type tasks** (LoCoMo, LongMemEval): use the `question_type` labels
  **exactly as they appear** in the previous `score_breakdown` keys; predict at
  the category level, not per individual episode.
- **no-task-type tasks** (if a tail defines none): name the specific episode
  `task_id`s you expect to flip pass↔fail, read from the prior
  `candidate_results/<id>.json` `tasks[]`.

Either way, next iter you self-grade these against the real outcome. You are
optimized on two things at once: the candidate's real **passrate** (keep
proposing genuinely better mechanisms — a no-op "safe" candidate scores zero on
this) and the **accuracy of your two-sided prediction**. These are
complementary, not a trade-off: aim for a bold, well-reasoned change AND an
honest prediction of both its upside and its downside.
