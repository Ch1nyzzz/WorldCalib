---
name: worldcalib-proposer-swebench-calib-addon
description: Calibration layer (self-distill world-model calibration, NO external critic) layered ONTO the base SWE-bench proposer contract — the append-only world_model_calibration.md protocol, prev_prediction.md, the per-instance pass↔fail prediction.md template (predict concrete per-instance_id flips, NOT score/passrate deltas), the mandatory per-issue triage of every currently-failing task, and the per-task self-grade distill block. Included by the swebench_calib arm immediately after _base_core.md.
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

**Predict per individual issue (`instance_id`), not per type.** SWE-bench has no
per-type axis — every issue is its own task and the `tasks[]` rows are the
individual code-fix instances (each `instance_id`'s `passed` is true/false). So
your prediction names the specific `instance_id`s a *general* mechanism should
flip to resolved, and the ones it might regress. This is a *calibration judgement
about a general mechanism* — which issues a general change is likely to flip —
and is distinct from overfitting: the runtime agent must never branch on a saved
`instance_id` / repo / file id or embed an issue's gold patch. **The prediction
may name instance_ids; the candidate code may not.**

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade. The base
`Analyze` step is **expanded** into a mandatory per-issue triage (below). **Before
the base `Design & implement` step**, write `prediction.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. Establish the ground-truth target solver model + base_url from the iteration
   message (and `./runtime_config.md` if it is staged).
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it, then read the previous
   iter's **real per-task** outcome from `candidate_results/<id>.json` — the
   `tasks[]` rows (each issue's `instance_id` + `score`/`passed`) — compared
   against the **base iter's** `tasks[]`, plus the trace evidence. **Self-grade
   per task**: for each `instance_id` you predicted to flip (fail→pass or
   pass→fail), did it actually flip? Which issues flipped **pass→fail that you did
   NOT name** (blind spots)? Did any issue you called **`model-limited` flip to
   pass**? For each wrong call, what does the trace say went differently? Then
   append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Per-task check (self): predicted flips hit X/Y — called right: <instance_ids>; called wrong: <instance_ids>
   - Blind-spot regressions: <instance_ids that flipped pass→fail and were NOT predicted>
   - Model-limited overruled: <instance_ids called model-limited that nonetheless flipped to pass — these were solvable after all>
   - Why mispredicted: <for each wrong call, the trace reason the real outcome differed>
   - Belief update: <one sentence revising the world model so the next per-task prediction is better>
   ```

   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the append —
   start cold.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest.

### Analyze — triage EVERY currently-failing issue, one by one

Do not jump to a hypothesis from aggregates. Enumerate **every** issue that is
currently unresolved (`passed` false in the latest frontier candidate's
`tasks[]`), and for **each** one:

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

You have triaged every failing issue, so predict at the **issue level**: name the
specific issues your change flips and tie each to that issue's trace evidence.

```
# iter_<THIS> prediction
## Candidate (one line)
## Base — the prior iter you rebuilt on (exact, e.g. iter_4, or `clean` for the seed)
## Why this change & why it optimizes the whole system
<the policy edit, the failure mode it attacks, and why the mechanism generalizes to unfamiliar issues — a general mechanism, not a per-instance hardcode>
## Mechanism — the behavioral change, and the failure mode (from the traces) it attacks
## Per-task effects — the falsifiable prediction
# List ONLY issues you expect to CHANGE (a pass↔fail flip), plus any at-risk
# issue you are deliberately protecting. One line per task, tied to its trace.
- <instance_id>: fail→pass — <the specific failure in this issue's trace the mechanism fixes>
- <instance_id>: pass→fail — <why this issue is now at risk>
- <instance_id>: pass→pass (protected) — <why this at-risk issue stays safe>   [optional]
## Model-limited (issues no harness change can solve)
# Where the trace shows the model itself cannot produce the fix — mark it here
# rather than listing it as fail→pass.
- <instance_id>: model-limited — <the capability the trace shows the model lacks>
## Falsification
<which named per-task flips, if they do NOT happen, refute the mechanism>
```

Ground each flip in that issue's trace, and read the `instance_id`s from the prior
`candidate_results/<id>.json` `tasks[]`. The prediction names issues; the **code
stays general** — never branch on an `instance_id` or embed a gold patch. Next
iter you self-grade these flips against the real per-task outcome.
