---
name: worldcalib-proposer-autolab-surface
description: AutoLab-specific evolving surface for the terminus-2 harness proposer — the terminus-2 agent harness you edit (prompt template, agent kwargs, config), the source-backed snapshot you point pending_eval.json at, and the autolab pending_eval conventions (exactly one candidate, extra.source_project_path, hypothesis fields). Spliced ahead of the shared base core; shared by both the autolab_calib and autolab_nowmc arms.
---

## What you are evolving

You are evolving the **terminus-2 agent harness** — the general-purpose coding /
engineering agent that AutoLab runs against each task. Each task = one real
optimization or implementation challenge (a problem statement in
`instruction.md` plus a prepared sandbox `environment/`); the agent works in the
sandbox, edits the target files the instruction names (e.g. `/app/predictor.py`),
and is scored by the task's verifier into a **continuous reward in [0, 1]**
(0.5 anchored to a human reference solution — see the task tail). The primary
metric is `average_score` — the mean reward across the tasks.

There is a frozen target LLM underneath (the solver model is fixed); you evolve
the *agent strategy wrapped around it* — the terminus-2 harness: how the agent is
prompted, how it is configured, and the agent kwargs it runs under. You do **not**
write per-task solutions and you do **not** touch any task's files.

The runtime candidate is the source-backed terminus-2 harness snapshot, loaded
from the edited snapshot named in `extra.source_project_path`. The editable
surface is the copied terminus-2 harness tree the iteration message names (plus
the optional generated wrapper directory). Concretely you may:

- reshape the harness **prompt template** — the system / instruction framing, how
  the task instruction and environment are presented, how prior steps and command
  output are rendered, how the agent is told to plan, verify, and finalize;
- adjust the harness **agent kwargs / config** the harness passes to terminus-2
  (e.g. `prompt_template`, `version`, and other terminus-2 kwargs) as supporting
  detail of a mechanism change — never as the substantive change on its own;
- restructure the harness **control flow** where the snapshot exposes it — step
  budgeting, when/how the model is called, how command output is
  truncated/summarized/fed back, retries, and the stop/finalize decision;
- add a verification or self-check step (e.g. run the task's visible data /
  starter check before finalizing, measure the metric the instruction states,
  iterate-then-keep-best);
- replace a mechanism wholesale (a different harness topology, context strategy,
  or information-flow structure).

**Do not assume any fixed prompt or harness structure** — choose the mechanism
that targets a real failure mode you observed in the traces.

## Hard environment boundaries (the harness must respect these)

- The harness must **never read any task's `solution/` directory** — it holds the
  reference solution and reading it is a cheat path; a candidate that routes the
  agent there is hard-rejected.
- The harness must **never edit a task's `tests/` directory or `task.toml`** — the
  verifier and its budgets are fixed platform inputs, not candidate surface.
- The harness must **not call the verifier or read `reward.json` / `reward.txt` /
  `results.json`** at inference time — these are the scorer's outputs, not agent
  inputs.
- Only the target files the task `instruction.md` names (e.g. `/app/predictor.py`)
  may be written **by the agent at task time**; the harness shapes *how* the agent
  does that, it does not pre-bake task answers.

## pending_eval.json conventions

The exact output path and JSON schema (with live substitutions) are in the
iteration message. Independent of those:

- The `candidates` array must contain **exactly one** candidate.
- `extra.source_project_path` must point at the edited terminus-2 harness
  snapshot the iteration message names.
- If you create a wrapper module under the generated directory, keep it small and
  route harness mechanisms through the clean edited snapshot.
- The `hypothesis` field must state: the observed failure mode being targeted,
  which specific tasks it should flip `fail→pass` (named per `task_id`, not a
  score-delta) and the cost impact, why the change should transfer beyond the
  scored tasks, and one currently-passing task it could regress (and why it
  won't).
