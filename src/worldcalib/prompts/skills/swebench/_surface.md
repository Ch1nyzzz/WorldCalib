---
name: worldcalib-proposer-swebench-surface
description: SWE-bench-specific evolving surface for the coding-agent proposer — the mini-SWE-agent control loop you edit, the source-backed snapshot you point pending_eval.json at, and the swebench pending_eval conventions (exactly one candidate, extra.source_project_path, hypothesis fields). Spliced ahead of the shared base core; shared by both the swebench_calib and swebench_nowmc arms.
---

## What you are evolving

You are evolving the **mini-SWE-agent control loop** — the coding agent that
resolves SWE-bench issues. Each task = one real software-engineering issue (a
problem statement plus a repo at a base commit); the agent works in a sandboxed
checkout, edits source, and produces a patch, scored by whether the repo's
**fail-to-pass and pass-to-pass tests** turn green. The primary metric is
`passrate` — the fraction of issues resolved.

There is a frozen target LLM underneath (the solver model is fixed); you evolve
the *agent strategy wrapped around it* — the control loop, prompts, tool/command
execution, observation handling, and submission logic.

The runtime candidate is the source-backed scaffold `mini_swe_agent_source`,
loaded from the edited snapshot named in `extra.source_project_path`. The
editable surface is the copied mini-SWE-agent source tree under
`candidate/upstream_source/mini-swe-agent/**` (plus the optional generated
wrapper directory). Concretely you may:

- reshape how the agent is prompted (system/instance templates, how observations
  and prior steps are rendered, how the issue and repo context are framed);
- restructure the control loop in `src/minisweagent/**` — step budgeting,
  when/how the model is called, how commands are parsed and executed, how command
  output is truncated/summarized/fed back, retries, and the stop/submit decision;
- add a verification or self-check step (e.g. run the repro before submitting,
  diff review, test-aware finalization);
- replace a mechanism wholesale (a different loop topology, context strategy, or
  information-flow structure).

**Do not assume any fixed prompt or loop structure** — choose the mechanism that
targets a real failure mode you observed in the traces.

## pending_eval.json conventions

The exact output path and JSON schema (with live substitutions) are in the
iteration message. Independent of those:

- The `candidates` array must contain **exactly one** candidate.
- `extra.source_project_path` must point at the edited mini-SWE-agent snapshot
  under `source_snapshot/candidate/upstream_source/mini-swe-agent`.
- If you create a wrapper module under the generated directory, keep it small and
  route source-backed mechanisms through the clean edited snapshot.
- The `hypothesis` field must state: the observed failure mode being targeted,
  the expected `passrate` direction and cost impact, why the change should
  transfer beyond the scored split, and one class of currently-passing issues it
  could break (and why it won't).
