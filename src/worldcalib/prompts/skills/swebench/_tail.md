---
name: worldcalib-proposer-swebench-tail
description: SWE-bench task tail — common coding-agent failure-mode bullets and the per-issue score_breakdown granularity note (each issue is its own category; the breakdown keys are the individual task_ids). Shared by both the swebench_calib and swebench_nowmc arms.
---

## SWE-bench task-specific hints

Each task hides a single real-world fix: the agent must localize the relevant
code from the issue text, make a minimal correct edit, and leave the rest of the
suite green. SWE-bench has **no per-type axis** — every issue is its own
category, so the `score_breakdown` keys in `candidate_results/<id>.json` are the
individual **`task_id`s** (e.g. `django__django-10097`) plus an aggregate `all`.
A repo prefix (`django__…`, `sympy__…`) is a weak grouping hint, not a scored
category.

Classify recurring failure modes from the traces (input to a *general* fix,
never a per-issue lookup):

- **mislocalization** — the agent edits the wrong file/function, or never finds
  the code the issue refers to, because search/navigation gave up too early or
  the issue's clues were not turned into concrete grep/inspect actions.
- **shallow fix / missed root cause** — a patch that addresses a symptom or one
  branch, leaving the fail-to-pass test red or breaking a pass-to-pass test.
- **no repro before editing** — the agent edits without first reproducing the
  reported failure, so it cannot tell whether its change actually fixes it; a
  mechanism that reproduces the bug and re-runs it after editing targets this.
- **regression from over-broad edits** — the change resolves the target issue but
  breaks previously-passing tests; a diff-review / test-aware finalization step
  targets this.
- **giving up early / budget mismanagement** — the agent stops (or loops on a
  failing command) before submitting a candidate patch; better step budgeting,
  command-output handling, or a graceful submit-best-so-far targets this.
- **submission/format loss** — the agent produced a working edit but the final
  patch is empty, malformed, or not captured; hardening the submit path targets
  this without changing the agent's reasoning.
