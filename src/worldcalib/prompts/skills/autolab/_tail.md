---
name: worldcalib-proposer-autolab-tail
description: AutoLab task tail — continuous-reward semantics (0.5 = human reference, gate 0.5), common terminus-2 harness failure-mode bullets, and the per-task granularity note (no per-category bucketing; the score_breakdown keys are the individual task_ids plus an aggregate all). Shared by both the autolab_calib and autolab_nowmc arms.
---

## AutoLab task-specific hints

Each AutoLab task is a single real engineering/optimization challenge: the agent
reads `instruction.md`, works in a prepared sandbox, edits the target file(s) the
instruction names, and the task's own verifier produces a **continuous reward in
[0, 1]**. The reward is calibrated so that **0.5 ≈ the human reference solution**
and **1.0 ≈ a perfect / ceiling result**; each task declares its own underlying
`metric` and `direction` in `task.toml`, but the harness only ever sees the
**already-normalized reward** — you never reason about raw metric direction. A
task counts as "passed" when `reward >= gate` (gate default **0.5**, i.e. at or
above the human reference); below that it is a partial or failing result. The
optimization *objective* is to raise the continuous reward across tasks; the
per-task *prediction* unit is the gate-defined pass↔fail flip (see the
calibration addon) — keep those two distinct, do not conflate them.

AutoLab is scored **per task, with no bucketing**. The `score_breakdown` keys in
`candidate_results/<id>.json` are the individual **`task_id`s** (e.g.
`adaptive_compression`, `fft_rust`, `flash_attention`) plus a single aggregate
`all` — there is deliberately **no per-category bucket**. The `[metadata].domain`
field (`system_optimization`, `model_development`, `puzzle_and_challenge`, `cuda`)
is at most a weak grouping hint for your own reasoning, never a scored category
and never a prediction unit.

Classify recurring harness failure modes from the traces (input to a *general*
fix, never a per-task lookup):

- **misread instruction / wrong target** — the agent edits the wrong file or
  misunderstands the required interface (class name, method signatures, output
  format the instruction specifies), so the verifier rejects the result outright
  (often a floor score); a mechanism that makes the agent restate the contract
  and the target file before coding targets this.
- **no measurement before finalizing** — the agent submits without running the
  task's visible data / starter check, so it cannot tell whether its change
  actually moved the metric; a mechanism that measures the stated metric on
  visible data and keeps the best variant targets this. This is the single
  highest-leverage class for a continuous-reward benchmark.
- **stops at the reference, not past it** — the agent produces a working solution
  around the 0.5 reference band and stops, leaving reward on the table; a
  mechanism that, once a valid solution exists, iterates to push the metric
  further (profile → improve → re-measure) targets the continuous tail.
- **regression / invalid output under edits** — a later edit breaks a
  previously-valid solution (e.g. an invalid distribution, a crash, a format the
  verifier can't parse), collapsing reward to the floor; a validate-then-keep /
  diff-review finalization step targets this.
- **budget mismanagement / giving up early** — the agent loops on a failing
  command or exhausts its step budget before finalizing a working solution;
  better step budgeting, command-output handling, or a graceful
  finalize-best-so-far targets this.
- **submission/format loss** — the agent produced a working edit but the target
  file is left empty, unsaved, or in a state the verifier can't load; hardening
  the finalize path targets this without changing the agent's reasoning.
