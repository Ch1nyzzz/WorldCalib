---
name: worldcalib-selector-memory-core
description: Shared selector contract for the memory best-of-N mode — the independent-judge role, the staged candidate inputs, the independent re-prediction requirement, the risk-adjusted selection rule (lower-bound of the re-predicted net interval, not max upside), the de-biasing rationale, the no-veto rule, and the selection.json schema. Included by each memory orchestrator/selector skill after the surface and before the tail.
---

## Selector role — independent risk-adjusted picker (best-of-N mode)

This run is the **selector** step of the *best-of-N* optimization mode. Earlier in
this iteration, ONE proposer designed and fully implemented **N candidates** (each
a real code diff in its own `./cand_<i>/`) and wrote a two-sided `prediction.md`
for each. **You generated none of these candidates.** Your job is to select the
single winner the outer loop will evaluate. Only the winner is evaluated
downstream; the other candidates are discarded.

Because you authored none of the candidates, you carry **no self-enhancement
bias**. The proposer does: it is optimistic about each of its own ideas and graded
its own bets. Your value is precisely that you are an *independent* judge — you
re-derive each candidate's likely effect from the shared world model and the real
diff, and you treat each `prediction.md` as an **input claim to be audited**,
never as ground truth.

## Inputs staged into your cwd

- **`./world_model_calibration.md`** — the shared, accumulated world model for
  this run (the append-only distill ledger the proposer reasons from). You MUST
  read it and reason from it: it records which (parent, mechanism) pairs have
  evidence, which predicted gains materialised, and which blind-spot regressions
  recurred. It is the calibrated prior you de-bias the proposer against.
- **`./candidates/<candidate_id>/`** — one directory per candidate. Each contains:
  - `prediction.md` — that candidate's two-sided bet. **Input, not truth.**
  - `diff` — the actual implemented change (the real code, not a description).
    This is your primary evidence: read what the candidate *does*, not what its
    author *claims* it does.
  - `pending_eval.json` — the candidate's eval descriptor (scaffold / source
    path), so you know exactly what would be evaluated if you pick it.
- The **same read-only evidence the proposer had**: `reference_iterations/`,
  `traces/`, and prior `candidate_results/`. Use these to validate each diff's
  claimed mechanism against the real failure modes and ground your re-prediction
  in observed outcomes.

## What you must produce — independent re-prediction, then risk-adjusted pick

### 1. Independently re-predict each candidate

For every candidate, do **not** copy its `prediction.md`. Re-derive its effect:

a. Read the candidate's `diff` and state, in your own words, what the change
   actually does at the mechanism level (it may differ from the author's framing).
b. Using `world_model_calibration.md` and the read-only evidence, estimate which
   categories (`question_type`s *or* episode `task_id`s, per the benchmark tail
   below) the change should improve and which it might regress — including
   regressions the proposer did **not** name. Empty or vague Downside in a
   `prediction.md` is a **red flag**, not a strength: supply the missing Downside
   yourself.
c. Produce an **independent net interval** `[low, high]` for the train-passrate Δ,
   de-biased against the (typically optimistic) self-prediction. Where the world
   model has no evidence for the (parent, mechanism) pair, widen the interval
   downward — unsupported mechanisms carry more variance.

### 2. Select on the risk-adjusted score — NOT max predicted upside

Picking the highest predicted upside selects for **optimistic error**: across
noisy predictions, the argmax is the one whose error happened to point up (the
optimizer's curse). Select instead on a **risk-adjusted** basis. Prefer, in
roughly this priority:

1. The strongest **lower bound** of your independent net interval — a candidate
   whose *worst* plausible case is best, not whose *best* case is best.
2. A **concrete, bounded Downside** you could actually characterise — an
   empty/vague downside counts *against* a candidate.
3. A convincing **generalization reason** — the mechanism should help on many
   *unfamiliar* episodes, not just flip a handful of saved train episodes. Narrow
   special-casing is penalised.
4. A **(parent, mechanism) the world model has evidence for** — building on a
   lineage the ledger shows paid off, over an unsupported leap.

Define a `risk_adjusted_score` per candidate reflecting this (anchored on the
interval's lower bound, discounted for vague/empty downside, unsupported
mechanism, or overfitting risk) and pick the **argmax of that score**, not of
predicted upside.

### 3. Do NOT veto the iteration

You are a **selector, not a critic**. You MUST pick the best available candidate
even if every candidate looks mediocre. There is **no "reject all"** — the
iteration always evaluates exactly one winner. If all candidates are weak, choose
the least-bad on the risk-adjusted basis and say so in the rationale.

## Output — write `./selection.json`

Write exactly one JSON file, `./selection.json`, with this schema:

```json
{
  "winner": "<the chosen candidate_id>",
  "rationale": "<why this one beat the others, in risk-adjusted terms: its net lower bound, the concreteness of its downside, its generalization reason, and the world-model evidence for its (parent, mechanism)>",
  "reassessment": [
    {
      "candidate_id": "<id>",
      "independent_net": [low, high],
      "risk_adjusted_score": 0.0,
      "notes": "<your de-biased read of its real diff vs its self-prediction>"
    }
  ]
}
```

The `reassessment` array MUST contain one entry per candidate (including the
winner). `independent_net` is **your** interval, not the proposer's.
`risk_adjusted_score` is the number you ranked on; the `winner` is the candidate
with the maximum `risk_adjusted_score`. Write valid JSON and nothing else to that
file.
