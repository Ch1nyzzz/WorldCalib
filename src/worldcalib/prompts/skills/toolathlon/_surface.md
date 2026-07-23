---
name: worldcalib-proposer-toolathlon-surface
description: Toolathlon backend contract for the agentic proposer — what the editable snapshot contains, the only hard constraints (model LOCKED; eval/gold/task-spec OFF-LIMITS; excluded tasks), and the pending_eval output contract. The proposer analyses all the feedback and patches the harness itself. Spliced ahead of the shared core.
---

## What you are evolving

You are optimizing the **agent harness** for Toolathlon — a broad benchmark where
the agent completes a real multi-app task (across ~32 MCP apps / 600+ tools) by
calling tools in a loop, graded by an **end-state check** of the affected
apps/files (`eval_res.json` `pass`, binary). The frozen LLM underneath
(deepseek-v4-flash) is the fixed SUT; you evolve the scaffold around it.

Per-task raw evidence is staged for you to read directly (the outcome record only
relays the benchmark's short verdict, never a diagnosed cause): each task's
`eval_res.json` (the benchmark's full verdict) and `run.log` (the verbatim
runtime log / traceback) sit under
`reference_iterations/iter_NNN/dumps/<candidate>/<task>/` and — for the iter you
built on — under `base_eval/dumps/<candidate>/<task>/`. On a failure whose cause
is not legible in the scores, read these, and read the `utils/**` code path that
produced the behavior — it is all white-box.

The runtime candidate is the source-backed scaffold `toolathlon_passthrough`,
loaded from an **editable snapshot** of the Toolathlon agent source. The editable
surface is:

- `utils/**` — the **entire agent implementation** (the function-calling loop,
  history/context compaction, tool dispatch, conversation/MCP machinery, …). You
  may edit any file under it **and add new files/modules** — the whole `utils/`
  tree propagates to the eval run, so new modules are importable.
- `agent_system_prompt.md` — the **global agent-policy system prompt** (one
  template shared by every task; the backend propagates your edit into every
  task dir at eval time). NOT the task spec.

Anything in that surface is harness you may rewrite however the evidence directs
— there is no prescribed lever or failure mode; read the source and the feedback
and decide. (The `run_parallel.py` orchestration, `scripts/`, the per-task entry
and the evaluator are NOT in the snapshot — they are eval machinery, off-limits.)

## Hard constraints (the only fences)

- **Model LOCKED to deepseek-v4-flash.** Never change the model / provider, add a
  second model, or alter the fixed sampling params (temp 0.6, top_p 1.0).
- **OFF-LIMITS — never edit, read for the answer, or bypass:** the evaluator
  (`utils/evaluation/…` and per-task eval logic) and each task's gold/spec
  (`tasks/finalpool/<task>/docs/user_system_prompt.md`, `task_config.json`, the
  rest of `docs/` and the task initialization). Do not branch on a task name or
  hardcode a task's answer — that is reward-hacking and is rejected. (The shared
  `agent_system_prompt.md` above is NOT the spec — it is editable policy.)
- **8 tasks are excluded** from train and test (5 k8s — no cluster; 3 snowflake —
  placeholder creds). Never design for them or treat their results as signal.

## pending_eval.json contract

The exact output path and schema are in the iteration message. Independent of those:

- exactly one candidate, with `"kind": "toolathlon_agent"` and
  `"scaffold_name": "toolathlon_passthrough"`;
- point `extra.source_project_path` at your edited snapshot of the Toolathlon
  source; `top_k` is a single integer (set to 1);
- `hypothesis`: the change you made, the expected passrate direction, and the
  evidence it came from.
