---
name: worldcalib-proposer-memory-base-core
description: Shared NON-calibration proposer contract for memory QA policies — objective, generalization rules (incl proposal-level guardrails), search space, workflow (no calibration step), evidence interface, hard rules, quality gate, edit scope. Included by every per-benchmark memory skill (both arms) via INCLUDE; the calib arm layers memory/_calib_addon.md on top. The memory surface is spliced ahead of this fragment.
---

## Objective

Expand the quality Pareto frontier over `passrate` and `average_score`.
`passrate` is the primary final metric; `average_score` is an optimization
objective because it captures near misses and often tracks generalization
better than a single threshold. `token_consuming` is a reported diagnostic, not
an objective — do not reduce recall solely to save tokens. Compression,
filtering, reranking, and context budgeting are valid when they are expected to
improve answer quality by removing noise or surfacing stronger evidence. The
per-`question_type` `score_breakdown` and the per-episode `tasks[]` rows (each
with a `task_id` + `score`/`passed`) in `candidate_results/<id>.json` are both
available to classify failure modes (see the benchmark-specific tail below).

## Generalization comes first — do not overfit the scored split

The split you are scored on during the loop is tiny (tens to low hundreds of
items) and is *not* the population you are optimizing for. Train `passrate` that
climbs while the candidate accumulates narrow heuristics is overfitting, not
progress. Optimize for what would still help on a held-out set an order of
magnitude larger.

The test for every change: **would this mechanism help a system facing many
unfamiliar tasks of the same kind?** If yes, keep it. If it only moves a handful
of the saved train items — a particular date phrasing, a particular entity, a
particular answer shape, a known annotation quirk — it is too specific; drop it.

- **No task-specific knowledge in runtime behavior.** Do not hardcode answers,
  conversation/task ids, entity names, dates, gold strings, or scorer quirks; do
  not branch on identifiers of saved tasks (`if "<name>" in question`).
- **Use traces and gold answers only to classify failure modes** — recurring
  evidence gaps, bad evidence ordering, retrieval misses — as the input to a
  *general* fix, never as a lookup table.
- **Watch for soft overfitting.** The real overfitting signal is *narrowness* —
  a change whose benefit is a handful of saved items via per-pattern boosts or
  per-keyword special cases, while the held-out set stalls. Judge a candidate by
  whether its mechanism would help unseen items.
- **When in doubt, make it more general**, and justify transfer in the
  candidate's `hypothesis` field.

### Proposal-level generalization guardrails

A proposal should target a **failure family**, not a task. Before editing code,
identify at least two independent evidence sources for the same mechanism-level
failure: different tasks, different conversations/sessions, different question
types, or a failed/successful contrast. If the evidence comes from only one task
or one surface pattern, do not implement a specialized runtime rule for it.

Prefer mechanisms that improve information flow across broad classes: retrieval
coverage, evidence diversity, conflict handling, temporal normalization,
deduplication, compression that preserves support, or answer grounding. You may
use any implementation form, including ranking rules, prompt/context packing,
or source changes, but make the transfer argument yourself: explain why the
mechanism follows from the failure family rather than from the surface details
of the sampled tasks.

First ask what unseen tasks would share this failure mode. Then inspect at least
one counterexample class that the change could hurt: already-correct tasks,
adjacent question types, or cases where the same cue means something different.
If you cannot name a plausible counterexample and explain why the mechanism
should not break it, revise the proposal until that reasoning is clear.

## Search space

The search space is the candidate source itself — arbitrary Python. You may
override or rewrite any function or method, restructure control flow, change how
the model is called, add or remove components, introduce new data structures, or
replace a mechanism wholesale. Anything expressible in Python is fair game.
Exploitation (refining the current mechanism) and exploration (a structurally
different mechanism) are both valid moves. A genuinely new mechanism — a
different memory ontology, state representation, retrieval strategy, or
information-flow topology — is a first-class candidate, not a last resort.

## Subagents

You can call a general-purpose subagent at any time you find it useful — it is a
tool available to you, optional and at your discretion.

## Workflow

1. **Analyze.** Read the available evidence (see *Evidence interface* below) and
   deep-read both failed *and* successful trajectories for recent iterations.
   Classify recurring failure modes — evidence gaps, bad evidence ordering,
   retrieval misses, context-packing or synthesis errors. This is the most
   important step.
2. **Hypothesize.** State one falsifiable hypothesis: a general mechanism that
   should improve held-out behavior, tied to a failure mode you classified.
3. **Design & implement** exactly one mechanism-level change in the editable
   source snapshot. One candidate tests one hypothesis.
4. **Smoke check.** Run a lightweight syntax/import check on the edited snapshot.
5. **Write `pending_eval.json`** with exactly one candidate.

## Evidence interface

Inspect the raw evidence directly: the `reference_iterations/iter_NNN/` bundles
(each with `candidate_results` and a `diff`) and the `traces/` files validate the
failure mode and the source change, and `candidate_results/<id>.json` carries the
outcome record — the per-`question_type` `score_breakdown` and the per-episode
`tasks[]` rows (each with `task_id` + `score`/`passed`) — to learn from.

## Hard rules (read before editing any source)

These three rules have specific, repeatable failure modes if you break them.
They are not stylistic preferences.

1. **No late imports of `worldcalib.*` inside method bodies.** Bind every
   `from worldcalib.scaffolds.base import X` / `from worldcalib.model import Y`
   / etc. at the **module top level**. The optimizer isolates the candidate's
   `sys.modules` only during scaffold *construction*; after construction it
   restores the host's `worldcalib.*` modules so the eval framework keeps
   working. A late `from worldcalib.scaffolds.base import answer_from_hits`
   inside `def answer(...)` resolves at call time to the **host's** `base.py`,
   which lacks any signature changes you made — call dies with
   `TypeError: unexpected keyword argument`, every task returns empty
   prediction, passrate goes to 0.0.

2. **Runtime scaffold code MUST NOT `import worldcalib.metrics`** (or any
   other scoring helper). The optimizer's `access_policy` hard-rejects any
   candidate whose `scaffolds/*.py` or `model.py` imports `worldcalib.metrics`
   with the marker `runtime code must not import OptiHarness scoring helpers`.
   Importing scoring code at runtime is a cheat path (gold labels visible
   inside the scaffold). The candidate is dropped before eval runs — your
   iter is wasted with no signal.

3. **When an iter failed, read the actual error before hypothesizing.** If
   `candidate_results/<iter>.json` shows every task has `prediction=""` and
   `prompt_tokens=0` / `completion_tokens=0`, the scaffold crashed at
   construction or call time — NOT a model/prompt issue. Read
   `candidate_results/<iter>.json → tasks[0].error` and the proposer's own
   `diff.patch` to figure out which import or signature broke. Do NOT write a
   speculative diagnosis like "wrong scaffold_name" when the real cause is a
   code-level error.

## Quality gate

Before writing `pending_eval.json`, verify the candidate:

- **is a real mechanism change**, not just a `top_k` / window / threshold /
  weight / prompt-length / context-budget variant. Parameter changes are allowed
  only as supporting detail of a mechanism change; a candidate whose substantive
  change is only a parameter will be rejected.
- **does not use gold answers at inference time** and does not hardcode
  benchmark-specific answers, conversation/task ids, entity names, dates, gold
  strings, or scorer quirks, and does not branch on identifiers of saved tasks.
- **would plausibly help a system facing many unfamiliar tasks** of the same
  kind — not just the tens-to-hundreds of items in the scored split. A change
  whose benefit is a handful of saved items, or a stack of narrow per-pattern
  special cases, is overfitting and will be rejected even if train `passrate`
  rises.
- **uses the isolated source snapshot** for source edits.

## Edit scope

Work inside the copied source snapshot and the optional generated wrapper
directory; the iteration message lists the exact editable paths. All copied
project source under `candidate/project_source/src/worldcalib/**` is editable,
including scaffolds, base classes, model/prompt helpers, dynamic-loading
helpers, and utils. Do not modify the outer optimizer, evaluator, metric/judge
code, raw data loaders, or run artifacts as part of a candidate.
