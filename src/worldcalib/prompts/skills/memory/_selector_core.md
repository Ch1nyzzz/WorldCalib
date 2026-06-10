---
name: worldcalib-selector-memory-core
description: Shared selector contract for the memory best-of-N mode — the independent-judge role, the staged candidate inputs, the independent PER-TASK re-prediction requirement (predict concrete per-task_id fail↔pass flips, NOT score/passrate deltas or net intervals), the per-task selection rule, the honest model-limited ceiling, the de-biasing rationale, the no-veto rule, and the selection.json schema. Included by each memory orchestrator/selector skill after the surface and before the tail.
---

## Selector role — independent per-task picker (best-of-N mode)

This run is the **selector** step of the *best-of-N* optimization mode. Earlier in
this iteration, ONE proposer designed and fully implemented **N candidates** (each
a real code diff in its own `./cand_<i>/`) and wrote a per-task `prediction.md`
for each. **You generated none of these candidates.** Your job is to select the
single winner the outer loop will evaluate. Only the winner is evaluated
downstream; the other candidates are discarded.

Because you authored none of the candidates, you carry **no self-enhancement
bias**. The proposer does: it is optimistic about each of its own ideas and graded
its own bets. Your value is precisely that you are an *independent* judge — you
re-derive each candidate's likely per-task effect from the shared world model and
the real diff, and you treat each `prediction.md` as an **input claim to be
audited**, never as ground truth.

## Inputs staged into your cwd

- **`./world_model_calibration.md`** — the shared, accumulated world model for
  this run (the append-only distill ledger the proposer reasons from). You MUST
  read it and reason from it: it records which (parent, mechanism) pairs have
  evidence, which predicted per-task flips materialised, which blind-spot
  regressions recurred, and which tasks are established as model-limited. It is
  the calibrated prior you de-bias the proposer against.
- **`./candidates/<candidate_id>/`** — one directory per candidate. Each contains:
  - `prediction.md` — that candidate's per-task bet. **Input, not truth.**
  - `diff` — the actual implemented change (the real code, not a description).
    This is your primary evidence: read what the candidate *does*, not what its
    author *claims* it does.
  - `pending_eval.json` — the candidate's eval descriptor (scaffold / source
    path), so you know exactly what would be evaluated if you pick it.
- The **same read-only evidence the proposer had**: `reference_iterations/`,
  `traces/`, and prior `candidate_results/` (the per-task `tasks[]` rows). Use
  these to validate each diff against the real per-task failure modes and ground
  your re-prediction in observed outcomes.

## What you must produce — independent per-task re-prediction, then pick

### 1. Independently re-predict each candidate's per-task flips

For every candidate, do **not** copy its `prediction.md`. Re-derive its effect:

a. Read the candidate's `diff` and state, in your own words, what the change
   actually does at the mechanism level (it may differ from the author's framing).
b. Using `world_model_calibration.md`, the prior `candidate_results/` `tasks[]`,
   and the traces, name the **specific `task_id`s** the change should flip
   `fail→pass` and the ones it might flip `pass→fail` — including regressions the
   proposer did **not** name. Tie every named flip to that task's own trace
   evidence; a flip you cannot ground in a specific cause is an optimistic guess.
c. **Honor the model-limited ceiling.** A claimed `fail→pass` on a task the world
   model (or this candidate's own honest read) has established as **model-limited**
   — unsolvable by any harness change — does not count. Prefer candidates that
   **honestly mark** the truly unsolvable tasks as model-limited.

Judge on concrete, trace-grounded per-task flips, not on a net interval, a
passrate Δ, or any aggregate/score number.

### 2. Select on the per-task flip profile

Pick the candidate with the strongest **concrete, well-evidenced per-task
profile**, in roughly this priority:

1. The most `fail→pass` flips that are each **grounded in a specific task trace**
   (ungrounded/optimistic flips do NOT count — discount them heavily).
2. The fewest **unprotected `pass→fail`** regressions (a candidate that names and
   bounds its risks beats one with a vague/empty downside).
3. **Honest model-limited marking** — a candidate that does not claim to flip
   tasks the evidence shows are unsolvable.
4. A convincing **generalization reason** — the mechanism should help many
   *unfamiliar* tasks, not just flip a handful of saved train tasks. Narrow
   special-casing is penalised.
5. A **(parent, mechanism) the world model has evidence for** — building on a
   lineage the ledger shows paid off, over an unsupported leap.

There is no single magic number: weigh the grounded net flip profile (grounded
`fail→pass` minus unprotected `pass→fail`) against generalization and evidence,
and pick the candidate whose concrete per-task case is strongest.

### 3. Do NOT veto the iteration

You are a **selector, not a critic**. You MUST pick the best available candidate
even if every candidate looks mediocre. There is **no "reject all"** — the
iteration always evaluates exactly one winner. If all candidates are weak, choose
the least-bad on the per-task basis and say so in the rationale.

## Output — write `./selection.json`

Write exactly one JSON file, `./selection.json`, with this schema:

```json
{
  "winner": "<the chosen candidate_id>",
  "rationale": "<why this one beat the others, in per-task terms: its grounded fail→pass flips, the concreteness/boundedness of its pass→fail risks, its honest model-limited marking, its generalization reason, and the world-model evidence for its (parent, mechanism)>",
  "reassessment": [
    {
      "candidate_id": "<id>",
      "expected_fail_to_pass": ["<task_id>", "..."],
      "expected_pass_to_fail": ["<task_id>", "..."],
      "expected_model_limited": ["<task_id>", "..."],
      "notes": "<your de-biased read of its real diff vs its self-prediction; flag any ungrounded/optimistic flips you discounted>"
    }
  ]
}
```

The `reassessment` array MUST contain one entry per candidate (including the
winner). The lists are **your** independent per-task calls, not the proposer's.
The `winner` is the candidate with the strongest grounded per-task profile. Write
valid JSON and nothing else to that file.
