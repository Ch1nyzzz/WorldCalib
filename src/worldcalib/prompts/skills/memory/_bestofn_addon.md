---
name: worldcalib-proposer-memory-bestofn-addon
description: Best-of-N calibration layer (self-distill WMC, NO external critic) for the single-proposer / external-selector variant on memory benchmarks. Identical to memory/_calib_addon.md (same world_model_calibration.md protocol, same self-grade, same two-sided prediction template) EXCEPT the proposer designs and fully implements N candidates (each in its own ./cand_<i>/ dir with its own prediction.md) and does NOT self-select — an independent selector picks the winner. Everything downstream (eval, prediction feedback, world-model chaining) is the same as the calib variant.
---

## Self-distill best-of-N calibration protocol (WorldCalib — NO external critic)

This is the calibration layer, applied **in addition to** the base Workflow. It
is **identical to the calib variant** in every respect — same self-distill world
model, same self-grade, same two-sided prediction — with exactly two
differences: (1) you produce **N candidates** this iter (each fully implemented,
each with its own prediction), and (2) an **independent selector** (not you)
picks the one to evaluate. There is **no external critic**.

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

**Predicting per question_type is not overfitting.** Naming which question
categories a change should improve or regress is a *calibration judgement about a
general mechanism* — distinct from overfitting: the runtime policy must never
branch on an episode index or embed an episode's answer. The prediction may name
categories (and, for benchmarks with no task-type axis, specific episode
`task_id`s); the code may not.

## How this layers onto the base Workflow

**Before the base `Analyze` step**, do the self-distill self-grade (below) —
exactly as the calib variant does. **In place of** the base Workflow's
`Design & implement` step (one candidate), design and fully implement **N
candidates** (below). The shared world model is read by you (the proposer) AND by
the selector — both reason from the same `world_model_calibration.md`.

### Before Analyze — self-distill the last iter (NO critic)

a. `cat ./runtime_config.md` for the ground-truth target model/base_url — do NOT
   infer model family from `src/worldcalib/model.py` defaults (they are
   launcher-overridden).
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists (iter ≥ 1): read it (last iter's selected
   winner's bet), then read that iter's **real** outcome from
   `candidate_results/<id>.json` — the `score_breakdown` (per `question_type`),
   or the per-episode `tasks[]` `score`/`passed` rows when the tail defines no
   task-type axis — plus the trace evidence. **Self-grade**: for each category
   (`question_type` *or* episode `task_id`) you listed under Upside, did it
   improve (Δ > +0.02, or a fail→pass flip)? For each Downside, did it regress
   (Δ < −0.02, or a pass→fail flip)? Which categories/episodes regressed that you
   did NOT name (blind spots)? Was your Net-bet direction right? Then append:

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

Produce **3 genuinely different** candidates. Each must be a *real,
mechanism-level* change to the memory scaffold source (not a trivial tweak), and
the three must target **different** failure families / mechanisms — not three
variants of one idea. A near-duplicate set defeats the purpose.

For **each** candidate `i` (i = 1, 2, 3), produce exactly what the calib variant
produces for its single candidate — just in its own dir:

1. **Implement it in its own dir.** Copy the entire editable `./source_snapshot/`
   to `./cand_<i>/source_snapshot/`, then apply *this candidate's* change to
   `./cand_<i>/source_snapshot/candidate/project_source/` (edit the source-backed
   surfaces named in the surface above — `memgpt_scaffold.py`, `model.py`, etc.).
   Each `./cand_<i>/source_snapshot/` is a complete, independently-loadable copy —
   do not share edits across candidates.
2. **Write its prediction** to `./cand_<i>/prediction.md`, using the world model,
   in exactly the calib template:

   ```
   # iter_<THIS> cand_<i> prediction
   ## Candidate (one line)
   ## Base — the prior iter this candidate builds on (exact, e.g. iter_4, or `clean`)
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
evaluate. Your job is three strong, distinct, fully-implemented bets.

### Write `pending_eval.json` — all N candidates

This **overrides** the surface's "exactly one candidate" rule: write exactly the
**3 candidates** as `{"candidates": [ ... ]}`. Each candidate object is exactly a
normal calib candidate (same fields, same `scaffold_name` / `build_tag` /
`hypothesis` / `changes` conventions from the surface), with its source paths
pointing at **its own** dir:

```
{"candidates": [
  {"name": "...", "scaffold_name": "memgpt_source", "source_snapshot_path": "./cand_1/source_snapshot", "extra": {"source_project_path": "./cand_1/source_snapshot/candidate/project_source"}, "hypothesis": "...", "changes": "...", ...},
  {"name": "...", "scaffold_name": "memgpt_source", "source_snapshot_path": "./cand_2/source_snapshot", "extra": {"source_project_path": "./cand_2/source_snapshot/candidate/project_source"}, ...},
  {"name": "...", "scaffold_name": "memgpt_source", "source_snapshot_path": "./cand_3/source_snapshot", "extra": {"source_project_path": "./cand_3/source_snapshot/candidate/project_source"}, ...}
]}
```

A **category** is whatever resolution the benchmark tail below specifies:

- **question_type tasks** (LoCoMo, LongMemEval): use the `question_type` labels
  **exactly as they appear** in the previous `score_breakdown` keys; predict at
  the category level, not per individual episode.
- **no-task-type tasks** (if a tail defines none): name the specific episode
  `task_id`s you expect to flip pass↔fail, read from the prior
  `candidate_results/<id>.json` `tasks[]`.

Next iter you self-grade the **selected winner's** prediction against the real
outcome — exactly as the calib variant does.
