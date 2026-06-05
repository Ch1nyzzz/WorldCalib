---
name: worldcalib-proposer-swebench-calib-addon
description: Calibration layer (self-distill world-model calibration, NO external critic) layered ONTO the base SWE-bench proposer contract — the append-only world_model_calibration.md protocol, prev_prediction.md, the per-issue Upside/Downside prediction.md template, the per-task (task_id) granularity rule, the mandatory per-issue triage of every currently-failing task, and the self-grade distill block. Included by the swebench_calib arm immediately after _base_core.md.
---

## Self-distill calibration protocol (WorldCalib — NO external critic)

This is the calibration layer, applied **in addition to** the base Workflow. This
run uses **self-distill** world-model calibration: there is **no external critic**
— you grade your own prediction. One append-only file per run, one prediction per
iter.

- **Per run, append-only: `./world_model_calibration.md`** (staged into your cwd;
  promoted back automatically). Seeded at iter 0 with an Observability template.
  Every iter ≥ 1 MUST append exactly one new `## iter_PREV -> iter_THIS distill`
  section. Never rewrite prior sections.
- **Previous iter's prediction: `./prev_prediction.md`** (staged if it exists).
  Your prior bet. There is **no** `critic_feedback.md` — you compare it yourself
  against the real outcome.
- **Per iter, your bet: `./prediction.md`** (written BEFORE editing source).

**Predict per individual issue (`task_id`), not per type.** SWE-bench has no
per-type axis — every issue is its own category and the `score_breakdown` keys
are the individual `task_id`s (plus `all`). So your prediction names the specific
`task_id`s a *general* mechanism should flip to resolved, and the ones it might
regress. This is a *calibration judgement about a general mechanism* — which
issues a general change is likely to flip — and is distinct from overfitting: the
runtime agent must never branch on a saved `task_id` / repo / file id or embed an
issue's gold patch. **The prediction may name task_ids; the candidate code may
not.**

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade. The base
`Analyze` step is **expanded** into a mandatory per-issue triage (below). **Before
the base `Design & implement` step**, write `prediction.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. Establish the ground-truth target solver model + base_url from the iteration
   message (and `./runtime_config.md` if it is staged).
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it, then read the previous
   iter's **real** outcome from `candidate_results/<id>.json` — the per-issue
   `score_breakdown` (each `task_id`'s passrate is 0.0 or 1.0) — plus the trace
   evidence. **Self-grade**: for each `task_id` you listed under Upside, did it
   flip fail→pass (passrate 0→1)? For each Downside `task_id`, did it regress
   pass→fail (1→0)? Which issues regressed that you did NOT name (blind spots)?
   Was your Net-bet direction right? Then append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Prediction check (self): Upside hit X/Y (flipped: <task_ids>); Downside named Z, regressed W; blind-spot regressions: <task_ids>
   - Outcome mismatch: <which predicted per-issue direction diverged; cite the score_breakdown 0/1 values>
   - Unresolved: <what this iter's evidence could not tell us>
   - Belief update: <one sentence revising the world model so the next prediction is better>
   ```

   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the append —
   start cold.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest.

### Analyze — triage EVERY currently-failing issue, one by one

Do not jump to a hypothesis from aggregates. Enumerate **every** issue that is
currently unresolved (passrate 0.0 in the latest frontier candidate's
`score_breakdown`), and for **each** one:

- open its latest trajectory (`traces/` / `reference_iterations/.../agent_runs/...`
  or the RunStore trace tools) and read what the agent actually did;
- write a one-line root-cause diagnosis tied to a failure mode from the task tail
  (mislocalization / shallow fix / no repro / regression / gave-up / submission
  loss / other) — citing the concrete step in the trajectory.

Record this per-issue triage (a short table is fine) before hypothesizing. The
recurring failure modes it surfaces — the ones shared across several issues — are
what a *general* mechanism change should target. An issue whose failure is truly
idiosyncratic is a poor target; prefer a mechanism that addresses a class.

### Before Design — write the self-graded bet `./prediction.md`

```
# iter_<THIS> prediction
## Candidate (one line)
## Base — the prior iter you rebuilt on (exact, e.g. iter_4, or `clean` for the seed)
## Mechanism (why it should move the metric)
## Upside — issues this should flip to RESOLVED (name task_ids, and why)
- <task_id>: <why this mechanism resolves this specific failure mode>
## Downside — issues that might REGRESS (name task_ids, incl. currently-passing ones, and why)
- <task_id>: <why this change could break it>  (an empty Downside is a red flag)
## Net bet
- Overall train passrate Δ: [low, high]
- Why upside > downside
## Falsification
<which predicted resolve/regression, if absent, refutes the mechanism>
```

A label is an exact `task_id` **as it appears in the previous `score_breakdown`
keys** (the task tail explains the key family). List the specific issues, not a
repo or "all". Next iter you self-grade these `task_id`s against the real 0/1
outcome.
