---
name: worldcalib-proposer-agentic-webshop-tail
description: WebShop task tail — failure-mode bullets, the dangling tool_call data artifact note, and the factual granularity note. Shared by both the webshop_calib and webshop_nowmc arms.
---

## WebShop task-specific hints

The WebShop task runs the agent against a simulated shopping site: it searches,
clicks through results, inspects product pages, selects options, and buys an item
that matches an instruction. This task has **no dataset task-type**: the
per-episode `tasks[]` rows in `candidate_results/<id>.json` (each carrying
`task_id` + `score`/`passed`) are the outcome granularity. The train split is
kept small (~30 episodes).

Classify recurring failure modes from the traces (input to a *general* fix,
never a lookup table):

- weak search queries — over-/under-specified search text that surfaces no
  matching product; not reformulating after empty results;
- premature purchase — buying before all required attributes (size, colour,
  price ceiling) are satisfied; ignoring the instruction's constraints;
- navigation loops — clicking back/forth between the same pages without
  progressing; not tracking which products were already inspected;
- option-selection misses — failing to set required product options before the
  buy action.

**Known data artifact — dangling `tool_call` episodes.** Roughly one in four
WebShop episodes ends with the conversation in a state where the last assistant
message has an unanswered `tool_call` (a dangling/unterminated tool turn). The
per-episode try/except isolates these as score 0 without crashing the batch, but
they also suppress the agent's real capability on those episodes. **Repairing a
dangling `tool_call` before returning is a legitimate, general mechanism** (e.g.
detect an unterminated tool turn in `query` and emit a well-formed terminating
message / synthesize the missing tool response) — it targets the protocol-level
failure, not specific episodes, so it generalizes.
