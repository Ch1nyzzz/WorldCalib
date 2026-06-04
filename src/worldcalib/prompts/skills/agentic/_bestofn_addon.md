---
name: worldcalib-proposer-agentic-bestofn-addon
description: Best-of-N calibration layer (self-distill WMC, NO external critic) for the single-proposer / external-selector variant. Same world_model_calibration.md protocol and two-sided prediction as the calib addon, but the proposer designs and FULLY IMPLEMENTS N distinct candidates (each in its own ./cand_<i>/ dir with its own prediction.md) and does NOT self-select — an independent selector picks the winner. Included by every per-task agentic bestofn skill immediately after _base_core.md.
---

## Self-distill best-of-N calibration protocol (WorldCalib — NO external critic)

This is the calibration layer, applied **in addition to** the base Workflow.
This run uses **self-distill** world-model calibration: there is **no external
critic**. You read and reason from the shared world model exactly as in the
single-candidate calib variant — the difference is that you produce **N
candidates** this iter and an **independent selector** (not you) picks the one
to evaluate.

- **Per run, append-only: `./world_model_calibration.md`** (staged into your
  cwd; promoted back automatically). Seeded at iter 0 with an Observability
  template. Every iter ≥ 1 MUST append exactly one new
  `## iter_PREV -> iter_THIS distill` section. Never rewrite prior sections.
- **Previous iter's prediction: `./prev_prediction.md`** (staged if it exists) —
  the prediction of last iter's **selected winner**. You compare it yourself
  against the real outcome; there is **no** `critic_feedback.md`.
- **Per iter: N candidates**, each fully implemented in its own `./cand_<i>/`
  dir with its own `./cand_<i>/prediction.md` (written BEFORE you edit that
  candidate's source). You do **not** choose between them.

**Predicting per episode is not overfitting.** For tasks with no dataset
task-type you will name specific episode `task_id`s a change should improve or
regress — a *calibration judgement about a general mechanism*, distinct from
overfitting: the runtime policy must never branch on an episode index or embed
an episode's answer. The prediction may name episodes; the code may not.

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade (below).
**In place of** the base Workflow's steps 2–3 (one hypothesis → implement one),
design and implement **N candidates** (below). The shared world model is read
by you (the proposer) AND by the selector — both reason from the same file.

### Before Analyze — self-distill the last iter (NO critic)

a. `cat ./runtime_config.md` for the ground-truth target model/base_url.
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it (the previous iter's
   selected winner's bet), then read that iter's **real** outcome from
   `candidate_results/<id>.json` — the `score_breakdown` (per task-type) or the
   per-episode `tasks[]` `score`/`passed` rows — plus the trace evidence.
   **Self-grade**: for each category you named under Upside, did it improve
   (Δ > +0.02, or a fail→pass flip)? For each Downside, did it regress
   (Δ < −0.02, or a pass→fail flip)? Which categories/episodes regressed that
   you did NOT name (blind spots)? Was the Net-bet direction right? Then append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Prediction check (self): Upside hit X/Y; Downside named Z, regressed W; blind-spot regressions: <categories>
   - Outcome mismatch: <which predicted per-category direction diverged; cite the score_breakdown numbers>
   - Unresolved: <what this iter's evidence could not tell us>
   - Belief update: <one sentence revising the world model so the next prediction is better>
   ```

   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the append.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest.

### Before Design — design and FULLY IMPLEMENT N distinct candidates

Produce **3 genuinely different** candidates. They must differ in **mechanism**
(each targets a *different* failure family — not three variants of one idea) and
may differ in **parent** (each may branch from a different prior iter; pick from
the `reference_iterations/` evidence). A near-duplicate set defeats the purpose.

For **each** candidate `i` (i = 1, 2, 3):

1. **Implement it in its own dir.** Copy the entire editable `./source_snapshot/`
   to `./cand_<i>/source_snapshot/`, then apply *this candidate's* mechanism-level
   change there (edit the `seed_passthrough.py` named in the surface, and the
   backend `base.py` only if a shared helper is genuinely needed). Each
   `./cand_<i>/source_snapshot/` is a complete, independently-loadable copy — do
   not share edits across candidates.
2. **Write its prediction** to `./cand_<i>/prediction.md`, using the world model,
   in exactly this shape (the selector and the next-iter self-grade read it):

   ```
   # iter_<THIS> cand_<i> prediction
   ## Candidate (one line)
   ## Base — the prior iter this candidate builds on (exact, e.g. iter_4, or `clean`)
   ## Why this change & why it optimizes the whole system
   <the policy edit, the failure mode it attacks, and why the mechanism generalizes to unfamiliar episodes — a general mechanism, not a per-episode patch>
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

3. **Smoke check** the candidate's edited snapshot (syntax/import).

**Do NOT pick a winner.** An independent selector reads all three candidates
(their real diffs + predictions + the world model) and chooses the one to
evaluate. Your job is to make three strong, distinct, fully-implemented bets.

### Write `pending_eval.json` — all N candidates

Write exactly the **N candidates** (not one) as `{"candidates": [ ... ]}`. Each
candidate object follows the surface's conventions, with its
`source_snapshot_path` set to **its own** `./cand_<i>/source_snapshot` so each is
loaded from the right implementation:

```
{"candidates": [
  {"name": "...", "scaffold_name": "...", "source_snapshot_path": "./cand_1/source_snapshot", "hypothesis": "...", "changes": "...", ...},
  {"name": "...", "scaffold_name": "...", "source_snapshot_path": "./cand_2/source_snapshot", ...},
  {"name": "...", "scaffold_name": "...", "source_snapshot_path": "./cand_3/source_snapshot", ...}
]}
```

A **category** is whatever resolution the task tail below specifies:

- **task-type tasks** (e.g. tau2, DB): use the **task-type labels exactly as
  they appear** in the previous `score_breakdown` keys; predict at the category
  level, not per individual episode.
- **per-episode tasks** (e.g. OS, WebShop, ALFWorld — no dataset task-type):
  name the specific episode `task_id`s (e.g. `os#3`) you expect to flip
  pass↔fail, read from the prior `candidate_results/<id>.json` `tasks[]`.

Next iter you self-grade the **selected winner's** prediction against the real
outcome.
