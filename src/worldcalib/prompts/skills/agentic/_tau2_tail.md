---
name: worldcalib-proposer-agentic-tau2-tail
description: tau2 telecom task tail — the reward_basis task-type labels and failure-mode bullets. Shared by both the tau2_calib and tau2_nowmc arms.
---

## tau2 telecom task-specific hints

The tau2 telecom domain has the agent resolve a customer's request by conversing
with a simulated user and acting on the telecom environment (lookups, plan/line
changes, troubleshooting) under a fixed domain policy. The `score_breakdown`
task-type labels are the task's **`reward_basis` signature** — these are the
per-task-type breakdown keys in `candidate_results/<id>.json`:

- `ENV_ASSERTION` — graded purely on final environment state;
- `ACTION+ENV_ASSERTION` — graded on the actions taken *and* the resulting
  environment state;
- `DB+COMMUNICATE` — graded on a database condition plus what the agent
  communicated to the user;
- `NL_ASSERTION` — graded on a natural-language assertion about the conversation.

Classify recurring failure modes from the traces (input to a *general* fix,
never a lookup table):

- **irreversible action without confirming intent** — performing a plan change,
  cancellation, or charge before verifying the user actually asked for it or
  before reading back the relevant state; the single biggest reward sink for
  `ACTION+ENV_ASSERTION` tasks;
- **misreading env state** — acting on a stale or wrong reading of the
  environment (wrong line, wrong plan), or not reading state back before
  asserting it to the user;
- **premature give-up / endless clarification** — abandoning before the goal
  state is reached, or looping on clarification with the user instead of acting;
- ignoring the domain policy's required steps; malformed tool calls; wrong tool
  choice.
