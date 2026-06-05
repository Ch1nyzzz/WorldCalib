---
name: worldcalib-proposer-memory-bestofn-addon
description: Best-of-N calibration layer (self-distill WMC, NO external critic) for the single-proposer / external-selector variant on memory benchmarks. Identical to memory/_calib_addon.md (same world_model_calibration.md protocol, same per-task self-grade, same per-task pass↔fail prediction template) EXCEPT the proposer designs and fully implements N candidates (each in its own ./cand_<i>/ dir with its own prediction.md) and does NOT self-select — an independent selector picks the winner. Everything downstream (eval, prediction feedback, world-model chaining) is the same as the calib variant.
---

## Self-distill best-of-N calibration protocol (WorldCalib — NO external critic)

This is the calibration layer, applied **in addition to** the base Workflow. It
is **identical to the calib variant** in every respect — same self-distill world
model, same per-task self-grade, same per-task pass↔fail prediction — with
exactly two differences: (1) you produce **N candidates** this iter (each fully
implemented, each with its own prediction), and (2) an **independent selector**
(not you) picks the one to evaluate. There is **no external critic**.

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

**Predicting per question is not overfitting.** Memory tasks are QUESTIONS;
naming the specific question `task_id`s a change should flip pass↔fail is a
*calibration judgement about a general mechanism* — distinct from overfitting:
the runtime policy must never branch on a question's `task_id` or embed its
answer. The prediction may name questions; the code may not.

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
   winner's bet), then read that iter's **real per-task** outcome from
   `candidate_results/<id>.json` — the `tasks[]` rows (each question's `task_id`
   + `score`/`passed`) — compared against the **base iter's** `tasks[]`, plus the
   trace evidence. **Self-grade per task**: for each `task_id` you predicted to
   flip (fail→pass or pass→fail), did it actually flip? Which questions flipped
   **pass→fail that you did NOT name** (blind spots)? Did any question you called
   **`model-limited` flip to pass**? For each wrong call, what does the trace say
   went differently? Then append:

   ```
   ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
   - Per-task check (self): predicted flips hit X/Y — called right: <task_ids>; called wrong: <task_ids>
   - Blind-spot regressions: <task_ids that flipped pass→fail and were NOT predicted>
   - Model-limited overruled: <task_ids called model-limited that nonetheless flipped to pass — these were solvable after all>
   - Why mispredicted: <for each wrong call, the trace reason the real outcome differed>
   - Belief update: <one sentence revising the world model so the next per-task prediction is better>
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
   in exactly the calib template — predict at the **question level**: name the
   specific questions this candidate flips, each tied to that question's trace
   evidence:

   ```
   # iter_<THIS> cand_<i> prediction
   ## Candidate (one line)
   ## Base — the prior iter this candidate builds on (exact, e.g. iter_4, or `clean`)
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
   # Where the trace shows the model itself lacks the reasoning/knowledge — mark
   # it here rather than listing it as fail→pass.
   - <task_id>: model-limited — <the capability the trace shows the model lacks>
   ## Falsification
   <which named per-task flips, if they do NOT happen, refute the mechanism>
   ```

   Ground each flip in that question's trace; where the trace shows the model
   itself lacks the reasoning/knowledge, mark it `model-limited` rather than
   listing it as `fail→pass`.

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

Ground each flip in that question's trace, and read the `task_id`s from the prior
`candidate_results/<id>.json` `tasks[]`. Each prediction names questions; the
**code stays general** — never branch on a `task_id` or embed an answer.

Next iter you self-grade the **selected winner's** prediction against the real
per-task outcome — exactly as the calib variant does.
