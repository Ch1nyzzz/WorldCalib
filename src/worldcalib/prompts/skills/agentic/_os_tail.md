---
name: worldcalib-proposer-agentic-os-tail
description: OS task tail — failure-mode bullets and the factual granularity note. Shared by both the os_calib and os_nowmc arms.
---

## OS task-specific hints

The OS task runs the agent against a Linux shell environment; episodes ask it to
inspect or modify the filesystem, run commands, and report an answer. This task
has **no dataset task-type**: the per-episode `tasks[]` rows in
`candidate_results/<id>.json` (each carrying `task_id` + `score`/`passed`) are
the outcome granularity. The train split is kept small (~30 episodes).

Classify recurring failure modes from the traces (input to a *general* fix,
never a lookup table):

- malformed shell commands — bad quoting/escaping, missing redirection, commands
  that need a working directory the agent never `cd`'d into;
- wrong tool choice — answering instead of acting, or running a command when it
  should commit a final answer;
- repetition / loops — re-running the same command after an identical error
  instead of reading the error and changing approach;
- filesystem misreads — assuming a path/permission exists; not verifying state
  after a mutation before reporting success;
- premature give-up — declaring done without checking the command's exit status
  or output.
