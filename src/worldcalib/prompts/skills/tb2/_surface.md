---
name: worldcalib-proposer-tb2-surface
description: Terminal-Bench 2.0 backend contract for the terminus-2 harness proposer — what the editable snapshot contains, the per-trial evidence Harbor writes, the only hard constraints (solver model LOCKED; tasks/verifier OFF-LIMITS; gold is evidence but must never be transmitted into the agent), and the pending_eval output contract. The proposer analyses the evidence and patches the harness itself. Spliced ahead of the shared tb2 base core; shared by both the tb2_calib and tb2_nowmc arms.
---

## What you are evolving

You are evolving the **terminus-2 harness** — the agent that solves Terminal-Bench
2.0 tasks. Each task is one command-line problem: the agent gets a natural-language
instruction and a Linux container, works in a tmux session, and is scored by whether
the task's own `tests/` verifier passes. The frozen solver LLM underneath is the
fixed SUT; you evolve the harness wrapped around it.

The runtime candidate is the source-backed harness loaded from the edited snapshot.
The editable surface is the copied terminus-2 agent package the iteration message
names — its control loop, prompt templates, parser, tmux/session handling,
verification and finalization logic, and any `agent_kwargs`. You may edit any file
in that tree **and add new files/modules**; the whole snapshot propagates to the
eval run, so new modules are importable. Only the `BaseAgent` interface Harbor
loads is fixed.

## Per-task evidence

Each task's outcome record carries:

- `question` — the task's `instruction.md`, verbatim: what the agent was asked to do.
- `prediction` — the agent's rollout, from Harbor's ATIF trajectory: every step, its
  source, and its message.
- `gold_answer` — the task's `solution/`, a reference solution to the same task.
- `error_tail` — the tail of the verifier's own test log.
- `test_summary` — the verifier's CTRF counts (`tests`, `passed`, `failed`, `skipped`).
- `final_pane` — the terminal as the agent left it, which is the state the verifier
  then judged.
- `rewards` / `k` — the per-trial rewards and how many trials ran.

Harbor's raw per-trial files are staged for you to read directly under
`reference_iterations/iter_NNN/dumps/<candidate>/<task>/` — plus, for the iter you
built on, `base_eval/dumps/<candidate>/<task>/`, and for the seed baseline,
`seed_eval/{eval,dumps}/` (its eval record and per-task dumps, same layout). Each
task's dump dir holds the files flat (no subdirectories):

- `test-stdout.txt` — the verifier's full test log.
- `ctrf.json` — the same results, structured per test.
- `trajectory.json` — the full ATIF trajectory.
- `terminus_2.pane` — the final terminal pane.
- `exception.txt` — present only when the trial crashed before the verifier ran.
- `trial.log` — Harbor's own log for the trial.

A file staged as `<name>.tail.txt` is an oversized original truncated to its
tail, with a header saying so.

Diagnose from these and from the harness source that produced the behavior; it is
all white-box. If the evidence for a claim is not in front of you, say the evidence
is missing rather than promoting a guess into a hypothesis.

## Hard constraints (the only fences)

These are in addition to the generic Hard rules below:

- **The solver model is LOCKED.** Never change the model / provider, add a second
  model, or alter the fixed sampling params.
- **OFF-LIMITS — never edit or bypass** the Terminal-Bench tasks or their grading:
  `instruction.md`, `environment/`, `solution/`, `tests/`, `task.toml`, the verifier,
  and the Harbor runner are not yours to change.
- **Gold is evidence, not an answer key.** Each record carries that task's
  `gold_answer`, and reading it to diagnose is expected and correct. What is
  rejected is **transmitting** it: the harness you ship must never read a task's
  `solution/` or `tests/` at inference time, never branch on a task id, and never
  encode a rule that holds only for the tasks whose solutions you have seen. The
  harness is scored on tasks you will never see.
- **The verifier decides.** A task scores 1 only when its tests all pass. Each task
  is run more than once and its score is the mean of those trials.

## pending_eval.json contract

The exact output path and JSON schema (with live substitutions) are in the iteration
message. Independent of those:

- The `candidates` array must contain **exactly one** candidate.
- `extra.source_project_path` must point at the edited terminus-2 snapshot.
- `top_k` is a single integer (set to 1).
- The `hypothesis` field: the change you made, the expected `average_score`
  direction and cost impact, and the evidence it came from.
