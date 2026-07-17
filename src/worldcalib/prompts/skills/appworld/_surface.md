---
name: worldcalib-proposer-appworld-surface
description: AppWorld backend contract for the interactive-coding-agent proposer — what the editable agent is, the only hard constraints (solver model LOCKED; evaluator/ground-truth OFF-LIMITS; keep the file worldcalib-free; preserve the solve() return contract), the staged raw evidence, and the pending_eval output contract. No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and edits the agent itself. Spliced ahead of the shared base core; shared by both the appworld_calib and appworld_nowmc arms.
---

## What you are evolving

You are evolving the **AppWorld interactive coding agent** — a ReAct *code* agent
that completes a supervisor's task by writing Python that calls app APIs. Each
task = one real multi-app request (across 9 apps / 457 APIs over a simulated
world of 106 people); the agent writes a snippet, it runs in a STATEFUL IPython
shell against the live world, the output comes back, and it iterates until it
calls `apis.supervisor.complete_task(...)`. Tasks are graded by AppWorld's
**programmatic state-based unit tests** (`world.evaluate().success`) — the primary
metric is `passrate` (task-goal completion). The frozen solver LLM underneath
(deepseek-v4-flash) is the fixed SUT; you evolve the agent wrapped around it.

Per-task raw evidence is staged for you to read directly (the outcome record only
relays a short verdict, never a diagnosed cause): each task's `result.json` (the
outcome + AppWorld's own test report) and `transcript.txt` (the FULL ReAct
conversation — every code block the agent wrote and every execution output) sit
under `reference_iterations/iter_NNN/dumps/<candidate>/<task>/` and — for the iter
you built on — under `base_eval/dumps/<candidate>/<task>/`. On a failure whose
cause is not legible in the scores, read the transcript and the agent source —
it is all white-box.

## The editable surface

The editable surface is a **single file**: `agent.py` (snapshotted at
`upstream_source/appworld/agent.py`). It is the whole agent policy — the ReAct
loop, the system prompt, the API-doc discovery strategy
(`apis.api_docs.show_api_descriptions` / `show_api_doc`), how it logs in via the
supervisor app, error handling, the step budget, and the SUT chat call. You may
rewrite it however the evidence directs and add new files/modules alongside it —
the whole snapshot dir propagates to the eval run, so new modules are importable.

There is no prescribed lever or failure mode: read the transcripts and the
feedback and decide. Natural directions the code-as-action paradigm opens
(discover them yourself, don't take them as a checklist): feeding execution
errors back to repair code, retrieving the right API docs before acting,
planning / decomposition, verifying state before `complete_task`, trimming
context — but only what the evidence supports.

## Hard constraints (the only fences)

- **The solver model is LOCKED.** Never change the model / provider / endpoint or
  the fixed sampling params. The agent must read the SUT only through its existing
  chat client.
- **OFF-LIMITS — never call, read for the answer, or bypass:** `world.evaluate()`,
  `world.task.ground_truth`, or anything that reveals the gold end-state. Grading
  is the harness's job. Do not branch on a `task_id` or hardcode a task's answer —
  that is reward-hacking and is rejected.
- **Keep `agent.py` worldcalib-free** (stdlib + `openai` + `appworld` only): it
  runs in the isolated eval interpreter and must NOT import `worldcalib`.
- **Preserve the entry contract:** keep a top-level `solve(world)` that drives the
  task via `world.execute(code)` / `world.task_completed()` and returns a dict
  with `steps`, `prompt_tokens`, `completion_tokens`, `error`, and `transcript`
  (the harness harvests tokens and stages the transcript as evidence).

## pending_eval.json contract

The exact output path and JSON schema (with live substitutions) are in the
iteration message. Independent of those:

- The `candidates` array must contain **exactly one** candidate, with
  `"kind": "appworld_agent"` and `"scaffold_name": "appworld_passthrough"`.
- `extra.source_project_path` must point at the edited snapshot dir under
  `source_snapshot/candidate/upstream_source/appworld` (the dir holding your
  edited `agent.py`).
- `top_k` is a single integer (set to 1).
- The `hypothesis` field: the change you made, the expected `passrate` direction
  and cost impact, and the evidence it came from.
