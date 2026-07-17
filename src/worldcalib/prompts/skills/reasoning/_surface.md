---
name: worldcalib-proposer-reasoning-surface
description: ARC-AGI-2-specific evolving surface for the reasoning proposer — what the editable solver snapshot contains (ArcScaffold.solve_task, seed_passthrough/base), the only hard constraints (single-shot only; test outputs/data-loader/evaluation OFF-LIMITS), and the pending_eval output contract (kind="arc_solver", scaffold_name="arc_passthrough"). No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and patches the solver itself. Spliced ahead of the shared base core; shared by both the reasoning_calib and reasoning_nowmc arms.
---

## What you are evolving

You are evolving the **solver** for ARC-AGI-2 — a single-shot abstract-reasoning
benchmark. Each task = a handful of train demonstration grid-pairs
(`input` -> `output`) plus one or more test `input` grids; the solver must
predict each test `output` grid, scored by **exact grid match, pass@2**. There
is **no agent loop, no tools, no memory retrieval, and no stateful environment**:
solving a task is a single chat call to the served target model. The frozen
target LLM underneath is fixed; you evolve the *strategy wrapped around it*.

The runtime candidate is the source-backed scaffold `arc_passthrough`, loaded
from the edited snapshot. Concretely you evolve an `ArcScaffold` subclass whose
`solve_task(*, train, test_inputs, client, config, max_tokens, max_attempts) ->
ArcSolveResult` produces, for each test input, an ordered list of candidate
output grids (the first `max_attempts` are scored pass@k). The editable surface:

- `src/worldcalib/reasoning/arc_scaffolds/seed_passthrough.py` — the solver. The
  seed `PassthroughArcScaffold` is a pure pass-through: it inherits the base
  `solve_task`, which for each test input builds a prompt via
  `build_arc_messages`, makes **one** `client.chat()` call at temperature 0.0,
  and `parse_grid`s the reply into a single attempt.
- `src/worldcalib/reasoning/arc_scaffolds/base.py` — `ArcScaffold` base plus the
  grid helpers (`format_grid`, `parse_grid`, `grids_equal`, `build_arc_messages`,
  `ArcSolveResult`). `self.config` is the `ScaffoldConfig`; one fresh scaffold
  runs per task (`fresh()`), so per-task state on `self` is safe.

Anything in that surface is solver you may rewrite however the evidence directs —
there is no prescribed lever or failure mode. You may edit any file in the
`arc_scaffolds` package **and add new files/modules**; the whole package
propagates to the eval run, so new modules are importable. Read the source and the
feedback and decide.

## ARC-specific hard rules

These are in addition to the generic Hard rules in the base core below:

- **Single-shot only.** The solver gets the served target model via
  `client.chat()`. Do not introduce an agent loop, tool calls, retrieval, or
  persisted cross-task memory. Multiple sampled calls inside one task (e.g. for
  self-consistency or a second pass@2 attempt) are fine; an interactive loop is
  not.
- **Never peek at test outputs.** The task json on disk contains gold `output`
  grids for the test entries, but the runner passes the scaffold **inputs only**.
  Do not reopen `metadata["task_path"]` (or any task json) to read test outputs,
  and do not import the evaluation/scoring code — both are cheat paths and the
  candidate is hard-rejected.
- **Do not edit the data loader, evaluation, or scoring** (`arc_data.py`,
  `arc_evaluation.py`, the grid-match / pass@2 logic). Layer strategy inside the
  solver only.
- **Importing stdlib is fine**; only late imports of `worldcalib.*` inside method
  bodies are forbidden. The `arc_scaffolds` package is snapshot-safe: import grid
  helpers from `.base`, never from `arc_data` / `arc_evaluation`.

## pending_eval.json conventions

The exact output path and schema are in the iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- The candidate MUST set `"kind": "arc_solver"`, `"benchmark": "arc_agi2"`, and
  `"scaffold_name": "arc_passthrough"`.
- Point `extra.source_project_path` at the edited snapshot project source when
  you modify
  `project_source/src/worldcalib/reasoning/arc_scaffolds/...`.
- `top_k` must be a single integer (unused by the solver; set to 1).
- `hypothesis`: the change you made, the expected passrate direction, and the
  evidence it came from.
