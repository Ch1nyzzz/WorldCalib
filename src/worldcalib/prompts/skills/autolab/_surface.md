---
name: worldcalib-proposer-autolab-surface
description: AutoLab-specific evolving surface for the agent-harness proposer — what the editable terminus-2 snapshot contains (a harbor BaseAgent you may keep, modify, or replace wholesale; only the BaseAgent interface is fixed), the harbor_contract read-only interface mirror, the only hard constraints (solver LOCKED; solution/tests/task.toml/verifier OFF-LIMITS), and the pending_eval output contract. No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and designs the agent itself. Spliced ahead of the shared base core; shared by both the autolab_calib and autolab_nowmc arms.
---

## What you are evolving

You are designing the **agent harness** that AutoLab runs against each task — the
general-purpose coding / engineering agent wrapped around a frozen solver LLM.
Each task = one real optimization or implementation challenge (a problem
statement in `instruction.md` plus a prepared sandbox `environment/`); the agent
works in the sandbox over a time budget, edits the target files the instruction
names (e.g. `/app/predictor.py`), and is scored by the task's verifier into a
**continuous reward in [0, 1]** (0.5 anchored to a human reference solution — see
the task tail). The primary metric is `average_score` across the tasks.

The solver LLM is FIXED; you evolve **the agent built around it**. The editable
candidate is the agent package at
`upstream_source/terminus2_agent/terminus_2/`. `terminus_2/terminus_2.py` holds
the CURRENT implementation — treat it as a **reference you may keep, modify, or
REPLACE WHOLESALE**, not a file you must minimally diff. The harbor runner loads
your edited copy via `--agent-import-path terminus_2.terminus_2:Terminus2`; set
`extra.source_project_path` to the ABSOLUTE package ROOT (parent of `terminus_2/`)
as `SNAPSHOT_AUTOLAB.md` states.

**The only fixed contract** is the harbor `BaseAgent` interface: keep the entry
class `class Terminus2(BaseAgent)` in `terminus_2/terminus_2.py` and implement
`name()`, `version()`, `async setup(environment)`, and
`async run(instruction, environment, context)`. Inside `run()` you use
`environment.exec(cmd, cwd=…, user=…) -> ExecResult(stdout, return_code)` to run
commands in the task container and a harbor LLM client (e.g. `LiteLLM`/`Chat`) to
call the solver model. The real interface definitions are mirrored READ-ONLY at
`upstream_source/harbor_contract/` (your sandbox has no harbor install) — read
them, and the reference `terminus_2.py`, before designing.

**Everything inside the agent is yours to design, and we prescribe NO design.**
You may edit any file under the package **and add new files/modules** — the whole
package propagates to the eval run, so new modules are importable. A from-scratch
redesign and a small targeted edit are equally valid candidates. There is no
prescribed lever or failure mode; read the reference `terminus_2.py`, the
`harbor_contract`, and the feedback, and decide. `pending_eval.json` `agent_kwargs`
(e.g. `parser_name` json|xml, `max_turns`, `temperature`) reach the constructor
and are available as supporting knobs.

You do **not** write per-task solutions and you do **not** touch any task's files.

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
- `extra.source_project_path` must point at the ABSOLUTE terminus-2 package ROOT
  (the parent of the edited `terminus_2/`), as named in `SNAPSHOT_AUTOLAB.md`.
- If you create a wrapper module under the generated directory, keep it small and
  route harness mechanisms through the clean edited snapshot.
- `hypothesis`: the change you made, which specific tasks it should flip
  `fail→pass` (named per `task_id`, not a score-delta), and the evidence it came
  from.
