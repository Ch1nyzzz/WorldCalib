---
name: worldcalib-proposer-swebench-surface
description: SWE-bench backend contract for the coding-agent proposer — what the editable mini-SWE-agent snapshot contains, the only hard constraints (solver model LOCKED; tests/grading OFF-LIMITS; reward-hacking ban), and the pending_eval output contract. No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and patches the agent itself. Spliced ahead of the shared base core; shared by both the swebench_calib and swebench_nowmc arms.
---

## What you are evolving

You are evolving the **mini-SWE-agent** — the coding agent that resolves
SWE-bench issues. Each task = one real software-engineering issue (a problem
statement plus a repo at a base commit); the agent works in a sandboxed
checkout, edits source, and produces a patch, scored by whether the repo's
**fail-to-pass and pass-to-pass tests** turn green. The primary metric is
`passrate` — the fraction of issues resolved. The frozen solver LLM underneath
is the fixed SUT; you evolve the agent wrapped around it.

Per-task raw evidence is staged for you to read directly (the outcome record only
relays a short verdict, never a diagnosed cause). Under
`reference_iterations/iter_NNN/dumps/<candidate>/<task>/` — and, for the iter you
built on, `base_eval/dumps/<candidate>/<task>/`:

- **`test_output.txt` — the test log itself: which test failed and how.** This is
  the file that answers "the patch applied and the tests still failed — why?".
  Read it FIRST on any such task. Its tail (the `FAILED <test> - <assertion>`
  lines and the counts) is also mirrored into the outcome record's `error_tail`.
- `miniswe_stdout.txt` — the agent's run log / traceback. This is what explains a
  **self-destruct** (no patch, a non-`Submitted` exit status).
- `official_eval_stdout.txt` / `official_eval_stderr.txt` — the run's **tally**
  ("resolved: 0"), not a verdict. It tells you THAT a task failed, never why.

A failure whose cause is "not legible in the scores" is the normal case, not the
exception: a clean patch that fails hidden tests looks identical, in the scores,
to a genuine model-capability ceiling. Do not infer a cause from the patch text
alone — open `test_output.txt` and the agent source that produced the behavior.
If the evidence for a claim is not in front of you, say the evidence is missing;
never promote a guess about the cause into a hypothesis.

The runtime candidate is the source-backed scaffold `mini_swe_agent_source`,
loaded from the edited snapshot named in `extra.source_project_path`. The
editable surface is the copied mini-SWE-agent source tree under
`candidate/upstream_source/mini-swe-agent/**` (the control loop in
`src/minisweagent/**`, the prompt/observation templates, tool/command execution,
submission logic, …) plus the optional generated wrapper directory. You may edit
any file in that tree **and add new files/modules** — the whole snapshot
propagates to the eval run, so new modules are importable.

Anything in that surface is agent you may rewrite however the evidence directs —
there is no prescribed lever or failure mode; read the source and the feedback
and decide.

## Hard constraints (the only fences)

- **The solver model is LOCKED.** Never change the model / provider, add a
  second model, or alter the fixed sampling params.
- **OFF-LIMITS — never edit, read for the answer, or bypass:** the SWE-bench
  test harness and grading (the fail-to-pass / pass-to-pass tests and the repo's
  evaluation machinery). Do not branch on a task / instance name or hardcode an
  issue's patch — that is reward-hacking and is rejected.

## pending_eval.json contract

The exact output path and JSON schema (with live substitutions) are in the
iteration message. Independent of those:

- The `candidates` array must contain **exactly one** candidate.
- `extra.source_project_path` must point at the edited mini-SWE-agent snapshot
  under `source_snapshot/candidate/upstream_source/mini-swe-agent`.
- If you create a wrapper module under the generated directory, keep it small and
  route source-backed mechanisms through the clean edited snapshot.
- `top_k` is a single integer (set to 1).
- The `hypothesis` field: the change you made, the expected `passrate` direction
  and cost impact, and the evidence it came from.
