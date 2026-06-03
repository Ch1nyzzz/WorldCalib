---
name: worldcalib-proposer-agentic-alfworld-tail
description: ALFWorld task tail — embodied-planning failure-mode bullets and the factual granularity note. Shared by both the alfworld_calib and alfworld_nowmc arms.
---

## ALFWorld task-specific hints

The ALFWorld task is embodied household planning in a text world: the agent
navigates rooms, finds and manipulates objects, and completes a goal (e.g. heat
an object and place it somewhere) through a sequence of grounded actions. This
task has **no dataset task-type**: the per-episode `tasks[]` rows in
`candidate_results/<id>.json` (each carrying `task_id` + `score`/`passed`) are
the outcome granularity. The train split is kept small (~30 episodes).

Classify recurring embodied-planning failure modes from the traces (input to a
*general* fix, never a lookup table):

- ungrounded actions — issuing an action whose object/receptacle is not present
  or not yet observed; acting on an object it never picked up;
- missing decomposition — skipping a required sub-step of a multi-stage goal
  (find → take → use appliance → place), or doing them out of order;
- search inefficiency — re-visiting already-searched receptacles; not tracking
  where it has looked;
- repetition / loops — repeating an action that produced no state change instead
  of reading the observation and replanning;
- premature give-up — declaring the goal done before the final placement /
  verification step succeeds.
