---
name: worldcalib-proposer-reasoning-surface
description: ARC-AGI-2-specific evolving surface for the reasoning proposer — the ArcScaffold.solve_task single-shot solver, editable seed_passthrough/base paths, ARC-specific hard rules, and pending_eval conventions (kind="arc_solver", scaffold_name="arc_passthrough"). Spliced ahead of the shared base core; shared by both the reasoning_calib and reasoning_nowmc arms.
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
  and `parse_grid`s the reply into a single attempt. Override `solve_task`,
  `build_arc_messages`, the grid parsing, or how the 2-attempt budget is spent to
  return a smarter solver.
- `src/worldcalib/reasoning/arc_scaffolds/base.py` — `ArcScaffold` base plus the
  grid helpers (`format_grid`, `parse_grid`, `grids_equal`, `build_arc_messages`,
  `ArcSolveResult`). `self.config` is the `ScaffoldConfig`; one fresh scaffold
  runs per task (`fresh()`), so per-task state on `self` is safe.

Things you can do (non-exhaustive — invent what the failure modes call for):

- reshape `build_arc_messages`: how the train demonstrations and the test input
  are rendered (grid formatting, axis/coordinate annotations, color legends,
  delta/diff hints), what instructions frame the transformation, how the model is
  asked to emit the answer grid so `parse_grid` recovers it reliably.
- restructure `solve_task`: add an explicit reasoning step before the grid, a
  self-consistency vote across samples, a second differentiated attempt for the
  pass@2 budget, a verification pass that re-derives the rule and checks it
  reproduces the train outputs, or a candidate re-ranking.
- harden parsing/repair so a correct-but-malformatted grid is not lost.

**Do not assume any fixed prompt structure** — choose the mechanism that targets
a real failure mode.

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
- The `hypothesis` field must state: expected passrate direction, the failure
  family targeted, at least two independent evidence sources, and one
  counterexample class the change was designed not to hurt.
