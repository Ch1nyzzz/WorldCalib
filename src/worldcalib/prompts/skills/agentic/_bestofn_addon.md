---
name: worldcalib-proposer-agentic-bestofn-addon
description: Best-of-N calibration layer (self-distill WMC, NO external critic) for the single-proposer / external-selector variant. Same world_model_calibration.md protocol and per-task pass↔fail prediction as the calib addon, but the proposer designs and FULLY IMPLEMENTS N distinct candidates (each in its own ./cand_<i>/ dir with its own prediction.md predicting concrete per-task_id flips, NOT score/passrate deltas) and does NOT self-select — an independent selector picks the winner. Included by every per-task agentic bestofn skill immediately after _base_core.md.
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
   selected winner's bet), then read that iter's **real per-task** outcome from
   `candidate_results/<id>.json` — the `tasks[]` rows (each task's `task_id` +
   `score`/`passed`) — compared against the **base iter's** `tasks[]`, plus the
   trace evidence. **Self-grade per task**: for each `task_id` the winner
   predicted to flip (fail→pass or pass→fail), did it actually flip? Which tasks
   flipped **pass→fail that were NOT named** (blind spots)? Did any task the winner
   called **`model-limited` flip to pass**? For each wrong call, what does the
   trace say went differently? Then append:

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
2. **Write its prediction** to `./cand_<i>/prediction.md`, using the world model.
   Predict at the **task level**: state the concrete effect of THIS candidate's
   change on the **specific tasks it touches**, each line tied to that task's own
   trace evidence. Use exactly this shape (the selector and the next-iter
   self-grade read it):

   ```
   # iter_<THIS> cand_<i> prediction
   ## Candidate (one line)
   ## Base — the prior iter this candidate builds on (exact, e.g. iter_4, or `clean`)
   ## Why this change & why it optimizes the whole system
   <the policy edit, the failure mode it attacks, and why the mechanism generalizes to unfamiliar episodes — a general mechanism, not a per-episode patch>
   ## Mechanism — the behavioral change, and the failure mode (from the traces) it attacks
   ## Per-task effects — the falsifiable prediction
   # List ONLY tasks you expect to CHANGE (a pass↔fail flip), plus any at-risk task
   # this candidate is deliberately protecting. One line per task, tied to its trace.
   - <task_id>: fail→pass — <the specific failure in this task's trace the mechanism fixes>
   - <task_id>: pass→fail — <why this task is now at risk>
   - <task_id>: pass→pass (protected) — <why this at-risk task stays safe>   [optional]
   ## Model-limited (tasks no harness change can solve)
   # Where the trace shows the model itself lacks the reasoning/knowledge — mark it
   # here rather than listing it as fail→pass.
   - <task_id>: model-limited — <the capability the trace shows the model lacks>
   ## Falsification
   <which named per-task flips, if they do NOT happen, refute the mechanism>
   ```

   Ground each flip in a specific cause in that task's trace, and read the
   `task_id`s from the prior `candidate_results/<id>.json` `tasks[]`. Where the
   trace shows the model itself cannot solve a task, mark it `model-limited`. The
   prediction names tasks; the **code stays general** — never branch on a
   `task_id` or embed an answer.

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

Every candidate predicts at the **individual task** resolution: name the specific
`task_id`s (e.g. `os#3`) you expect to flip pass↔fail, read from the prior
`candidate_results/<id>.json` `tasks[]`. There is no aggregate / per-category /
score-Δ prediction.

Next iter you self-grade the **selected winner's** per-task prediction against the
real per-task outcome.
