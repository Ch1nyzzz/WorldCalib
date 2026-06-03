---
name: worldcalib-proposer-reasoning-tail
description: ARC-AGI-2 task tail — failure-mode bullets and the factual grid-size-change task-type-label granularity note. Shared by both the reasoning_calib and reasoning_nowmc arms.
---

## ARC-AGI-2 task-specific hints

Each ARC task hides a single abstract transformation rule that maps every train
`input` to its `output`; the solver must infer that rule from a few
demonstrations and apply it to the test input(s). The `score_breakdown`
task-type labels are the **output grid-size-change signature**, derived from the
train demos (output area vs input area across pairs) — these are the
per-task-type breakdown keys in `candidate_results/<id>.json`:

- `same_size` — every train output has the same area as its input (in-place
  recolor / overlay / local edits; geometry preserved);
- `grow` — every train output is larger than its input (tiling, repetition,
  reflection-expansion, framing);
- `shrink` — every train output is smaller than its input (cropping, extraction,
  downsampling, object isolation);
- `variable` — mixed or undetermined size relationship across pairs (the rule's
  output size depends on content, the hardest size class to predict).

Classify recurring failure modes from the traces (input to a *general* fix,
never a lookup table):

- **wrong output dimensions** — the model emits a grid of the wrong shape; most
  damaging for `grow` / `shrink` / `variable`, where inferring the target size is
  itself part of the rule. A mechanism that makes the model reason about and
  state the output dimensions before filling cells targets this directly.
- **right rule, wrong cells** — the transformation is understood but applied with
  off-by-one placement, a mis-mapped color, or a missed object; common on
  `same_size` tasks.
- **rule mis-inferred from too few demos** — over-fitting one demonstration and
  ignoring a counterexample pair; a verify-against-all-train-pairs step targets
  this.
- **parsing / formatting loss** — the model reasons correctly but emits the grid
  in a shape `parse_grid` cannot recover (prose around it, ragged rows, wrong
  separator); hardening the answer format or repair targets this without changing
  the model's reasoning.
- **squandered pass@2 budget** — both attempts are near-identical, so the second
  attempt adds no coverage; differentiating the second attempt (different
  framing, sample, or hypothesis) targets this.
