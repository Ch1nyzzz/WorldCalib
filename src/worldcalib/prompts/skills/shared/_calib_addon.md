---
name: worldcalib-proposer-calibration-addon
description: Shared self-distilled world-model calibration contract. This is the single calibrated-arm addition: maintain falsifiable beliefs and run each iteration as predict, observe, and correct.
---

## Self-distill environment calibration — the calib arm's one difference

The plain arm reads the feedback and edits the agent. The calib arm does one extra
thing: it maintains an explicit, **falsifiable model of the environment** and lets
that model drive every candidate. A candidate is an *experiment* that tests and
exploits the model. **The goal is unchanged from the base Objective: maximize the
harness's passrate.** The world model is the *instrument* for getting there, never
an end in itself — you maintain an accurate model because that is how you reliably
pick interventions that actually raise passrate instead of chasing noise. This is
**self-distill** — there is no external critic, no `critic_feedback.md`: you
predict, observe, and correct your own model.

Everything below is one idea — **each iteration is one experiment on the model,
run as predict → observe → correct**. The disciplines you might expect as
separate gadgets (reading raw evidence, choosing what to try next, dropping a
dead direction) are just facets of running that experiment honestly.

## The model lives in `world_model_calibration.md`

Files staged into cwd (and promoted back) each iter:
- **`./world_model_calibration.md`** — the model (below).
- **`./prev_prediction.md`** — your previous iter's bet (present from iter ≥ 1).
  You grade it yourself.
- **`./prev_aggregate_grade.md`** — the harness's mechanical read of your
  previous iter's `## Aggregate bet (machine)` (present once a graded bet
  exists). An instrument reading, not a veto: grade yourself FIRST, then
  reconcile — when your grade and the mechanical read disagree, the
  disagreement is itself evidence about how you read the environment.
- **`./predictions_history/iter_NNN.md`** — every earlier iter's
  `prediction.md`, verbatim, so you can audit your own longitudinal
  calibration directly instead of trusting your HISTORY summaries of it.
- **`./prediction.md`** — this iter's bet, written BEFORE you edit any source.
- **`./runtime_config.md`** — ground-truth target model / base_url.
- **`./seed_task_table.json`** — one mechanical row per seed task: both trial
  scores, stable/unstable, CTRF passed/failed counts, timed-out, crashed,
  duration, episode count. Facts only, no tier and no cause — those are what
  you derive. Present from iter 1 on; the entry point for the Task map below.

Layout — a **mutable HEAD** + an **append-only HISTORY**, split at the first
`## iter_` heading:

- **HEAD** (rewritten in place every iter — the live model), these lean sections:
  - **Beliefs** — falsifiable facts about the environment, each:
    `[E<n>] <claim> | conf:<0.0–1.0> | status:<hypothesis|confirmed|refuted|unverifiable> | evidence:<openable pointers + task_ids> | mass:~<N> tasks it explains`
    The evidence field must carry at least one pointer you can OPEN from this
    workspace (a trace/span file, a `dumps/` file, a `task_score_matrix.json`
    row) — never task_ids alone. A belief whose pointers cannot be opened here
    is `unverifiable`: cap its conf at 0.3 until you re-ground it in evidence
    you actually read this iter. This is what keeps the model auditable — a
    later iter must be able to reopen your evidence and re-check the claim.
    A claim may say where it lives or whether it looks fixable when you actually
    know — but **start from an empty Beliefs list and fill it only from THIS
    run's evidence. Never pre-seed it with guessed failure modes**: an assumed
    fact becomes an anchor you then burn iterations chasing. Prefer 5
    high-confidence beliefs over 20 vague ones.
  - **Experiments** — what you've tried against each belief and the verdict, so
    the model records what each experiment showed: `- <belief E<n>>: <experiment> → <held|flat|harmful>`.
  - **Calibration** — how well your recent predictions held (behavioral H/N,
    aggregate H/N over the last ~4). This is the meta-signal for the next
    experiment: weak calibration means trust the model less and buy information.
  - **Task map** — one line per task, a coarse and refutable estimate of how
    *tractable* each task is for a harness change, filled from THIS run's
    evidence (never pre-seeded):
    `[T] <task_id> | tier:<gradient|ceiling|env|noise|unknown> | conf:<0.0–1.0> | why:<one clause tied to evidence> | evidence:<openable pointer> | seen:iter_<N>`
    A tier carries an openable pointer exactly like a belief, so a later iter
    can reopen it and recheck. The tiers estimate optimization tractability,
    not failure mechanism:
    - `gradient` — the harness plausibly moves it: a near-miss (some sub-tests
      or partial credit already pass) or a stable-fail/unstable whose cause is
      legible and lives in the editable surface.
    - `ceiling` — all four evidence layers were present (question, full
      rollout, consequences, gold) and you still cannot name a harness change
      that would move it; the blocker reads as the SUT's own capability. This
      is the WEAKEST tier: you can never certify a wall, only observe one has
      not moved. Cap conf ≤0.7, keep it refutable, and any later score or
      sub-test movement on that task drops it straight back to `unknown`.
    - `env` — the zero is not the SUT's: verifier setup failed, the network was
      cut, the sandbox ran out of disk. A fact about the environment, never the
      model — excluded from every aggregate bet.
    - `noise` — the runs disagree and each rollout self-reports success against
      no checkable ground truth; the flip grades ~random and carries no gain
      signal.
    - `unknown` — the default until evidence earns a tier. An untriaged task is
      `unknown`, never `ceiling` by assumption.
    Cover every seed task once at iter 1 (below); after that, revise only the
    tiers new evidence actually touches — do not re-triage the whole set.
  - **Residual** — the model's uncovered *tractable* failure mass, recomputed
    every iter: `<k>/<n> gradient-tier stable-fail tasks unclaimed by any
    belief: <task_ids>`. A stable-fail task counts as claimed only if some
    belief's mass includes it; ceiling/env/noise tasks are outside the residual
    because no harness change is expected to move them. The unclaimed block is
    where new beliefs come from — which part of it to buy next is your
    judgment, but the number itself is not optional: a model that is precise on
    2 beliefs while half the tractable failure mass is unclaimed is not yet a
    good model.
- **HISTORY** (append-only, from the first `## iter_` on) — one
  `## iter_PREV -> iter_THIS distill` block per iter. **Never edit or delete a
  prior block**; the harness refuses to let HISTORY shrink.

## Each iteration is one experiment: predict → observe → correct

An experiment is worth running for exactly one of two reasons — it **buys
information** (resolves uncertainty about something that matters) or it **cashes
a gain** (acts on a confident belief to move passrate). That is the whole loop.

### Correct (before the base `Analyze`) — grade the last experiment, update the model

a. `cat ./runtime_config.md` for the ground-truth target model/base_url.
b. `cat ./world_model_calibration.md`. If missing, abort and report.
c. If `./prev_prediction.md` exists: read the **environment claim** it bet, then
   read the real outcome from `candidate_results/<id>.json` `tasks[]` vs the
   **base iter's** `tasks[]`, plus the traces.

   **Validate the measurement BEFORE grading it.** Open at least one trace /
   transcript from the candidate's own eval and confirm the candidate's
   distinctive change was actually live in it (its changed prompt text, its new
   behavioral marker, its code path — something only the candidate, not the
   base, would produce). An eval can silently run the wrong artifact; its
   numbers then measure nothing about your mechanism. If you cannot find
   positive evidence the change was live, the iteration is **VOID for the
   environment model**: record it as a wiring miss in the distill block, do
   NOT move any belief's conf from its numbers (in either direction), fix the
   wiring, and re-run the experiment. A VOID iter is a fact about the harness,
   never about the environment.

   **Grade against the RAW evidence, not the agent's final message** — and RAW evidence is everything white-box: the
   tool-call OUTPUTS, the trace turns, AND the harness source / control flow you
   can read directly. The harness control flow IS part of the environment you are
   modelling — not off-limits, not a black box. When a failure's cause is not
   legible in the outputs, READ THE CODE PATH that produced it (the loop, the
   context/tool machinery in the editable surface), or add a diagnostic probe and
   re-run, rather than inferring the mechanism from aggregate symptoms. Grade on
   two de-noised axes:

   - **Behavioral (from traces):** did the agent actually do what the claim
     implied on the targeted subset?
   - **Aggregate (de-noised):** on the subset (~N tasks as a group), did mean
     stable-pass / mean score move by the predicted amount, with ≤m stable
     regressions? Use **stable** outcomes only — a task whose runs (or cross-iter
     `task_score_matrix.json` row) disagree is UNSTABLE: exclude it, never read
     it as a flip. Averaging over the subset cancels per-task noise.

   Grade against the WHOLE history, not just the last step. A belief's claim
   about a subset must be consistent with those tasks' full
   `task_score_matrix.json` rows — a task the belief calls blocked that passed
   in some earlier iter refutes or bounds the claim. And when a row shows the
   same task passing under one candidate and failing under another, the two
   rollouts plus the known scaffold diff between them
   (`reference_iterations/iter_NNN/` evidence + its `diff_digest.md`) form a
   controlled comparison: read BOTH sides, not just the failing one. It is the
   highest-information evidence in the workspace and costs two file reads.

   If `./prev_aggregate_grade.md` exists, reconcile it with your own grade
   before writing the model update: agreement raises trust in your reading;
   disagreement means your reading of the environment is biased somewhere —
   find where before you touch conf values.

   The experiment resolves to ONE verdict, and **picking the right verdict IS
   the correction** — each has its own evidence bar:

   - **VOID** — the measurement check above found no proof the candidate was
     live. A fact about the harness, never the environment: no belief moves in
     either direction; fix the wiring, re-run.
   - **Inert** — the candidate was live but its mechanism's behavioral
     signature never appears in the traces (the mechanism itself is broken).
     Nothing learned about the environment — fix and re-run.
   - **Held** — the behavior appeared AND the subset moved as predicted: raise
     conf, flip to `confirmed`.
   - **Flat** — the behavior appeared, the subset didn't move: the layer you
     blamed is not the bottleneck; lower the belief's conf. Flat means
     *train-invisible*, not *worthless*: if the traces show correct
     micro-decisions where the mechanism fires, you MAY retain it in the stack
     — belief scoped `aggregate-invisible on train`, conf ≤0.5,
     status:hypothesis. Retention is earned by that behavioral evidence alone
     ("should generalize in theory" with no trace of it firing is clutter —
     revert), and retained mechanisms are the first suspects when a later
     experiment on the stack regresses.
   - **Harmful / refuted** — needs BOTH layers: the aggregate drop AND trace
     turns you can point at where the change produced the worse behavior. An
     aggregate drop with no behavioral trace of its mechanism is **suspect,
     not refutation** — one eval is one noisy draw; the drop may be harness or
     noise, not your change. Write the anomaly down, keep the status, demote
     only when a second look corroborates. One poisoned measurement
     internalized as a belief costs every later iteration that trusts it —
     beliefs must be harder to poison than scores.
   - **Surface illusion** — the feedback's pre-baked label (a crash headline,
     a final message that "looks like" failure) disagrees with the layer
     underneath: the tool's actual output or the harness code path. Read that
     lower layer and re-attribute the belief there; a label is itself a
     surface claim, never the cause.

   Repeated disconfirmation simply keeps lowering a belief — **never read it as
   "the SUT is incapable."** You cannot certify a wall; you can only observe that
   a belief stopped paying and look elsewhere or one layer down.

   Then do TWO writes:
   1. **Rewrite the HEAD in place** — update the cited belief's conf/status,
      add/split beliefs, update the Experiments log, recompute Calibration.
   2. **Append one distill block to HISTORY** (the grading + reasoning that
      justified the HEAD edit — not a restatement of the HEAD):
      ```
      ## iter_<PREV> -> iter_<THIS> distill (<ISO-8601 UTC>)
      - Experiment: information|gain / refine|explore — <one line>
      - Measurement: <wired in — candidate's change seen live at <openable pointer> | VOID (wiring miss — no belief updated from these numbers)>
      - Claim graded: "<the env claim from prev_prediction>" relied on E<n>
      - Behavioral (from traces): <held | inert (never fired) | flat (fired, subset unmoved) | surface-illusion → lower layer>
      - Aggregate (de-noised): subset (~<N>) predicted <±k>, got <actual>; stable regressions <r> (≤<m>)
      - Model update: E<n> conf <old→new>, status <→>; new/split beliefs: <E<m> ...>
      - Unstable (excluded): <task_ids whose runs / cross-iter row disagree>
      - Blind-spot: <task_ids that stably flipped pass→fail and were NOT anticipated → which belief missed them>
      - Task map: <tiers changed this iter, e.g. "T foo ceiling→unknown (sub-tests moved 2→4)"; "none" if unchanged>
      - Residual: <k>/<n> gradient-tier stable-fail unclaimed (prev iter: <k_prev>/<n_prev>)
      ```
   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the grade
   but still **bootstrap the HEAD** from the seed's traces (beliefs as
   `hypothesis`, Calibration 0/0) and append a `## iter_000 -> iter_001 distill`
   block marked bootstrap. This bootstrap is the one time you **cover every seed
   task in the Task map**: start from `seed_task_table.json` for the mechanical
   row of each task, then open the evidence of the failing and unstable ones to
   assign a tier (the passing ones can take their tier from the table alone).
   Reading many tasks here is cheap and worth delegating to a subagent — the
   point is to spend the later iterations' deep reads on the `gradient`/`unknown`
   tasks and not re-litigate `ceiling`/`env`/`noise` every round. Later iters do
   NOT re-triage the whole set; they revise only the tiers new evidence touches.
d. **Refute stale tiers.** Any task whose score or CTRF sub-test counts moved
   since it was last `seen` — read straight off `task_score_matrix.json` and the
   new eval — drops to `unknown` and is re-triaged from the movement, whatever
   tier it held. A `ceiling`/`env`/`noise` label that a later rollout contradicts
   was a wrong estimate, not a property of the task; the movement is the
   evidence that retires it.
e. Re-read `./world_model_calibration.md` so the rest reasons from the latest HEAD.

### Choose the next experiment — let the model decide

No scheduling rule, no family bookkeeping, no coverage quota. The next experiment
is simply whatever your current model makes most valuable: where the model is
**uncertain about something that matters**, run the cheapest experiment that
resolves it (it buys information, even if it won't move the score much); where the
model is **confident**, run the experiment that acts on it (it cashes a gain).
State which — information or gain — in the prediction.

How you spread experiments across competing directions, and when to go deep on
one versus widen to another, is **your research judgment from the evidence** —
not a rule the harness imposes. An idea whose experiment moved nothing has simply
lowered its own belief's confidence in the `Correct` step above; that updated
model is the only thing that decides whether it is still worth revisiting.

### Predict (before the base `Design`) — write the bet to `./prediction.md`

```
# iter_<THIS> prediction
## Experiment: information | gain  /  refine | explore — <one line why>
## Candidate (one line)
## Base — the prior iter you built on (e.g. iter_4, or `clean` for the seed)
## Belief in play
E<n>: "<the belief this experiment tests or exploits>" | status:<hypothesis|confirmed> | conf:<x>
  (information: which way this experiment resolves it. gain: why a confident belief implies this fix.)
## Mechanism — the behavioral change
<the edit; what the agent will DO differently on this subset; why it generalizes>
## Environment claim (the bet)
"<what the ENVIRONMENT will do — e.g. 'the bottleneck on subset S is L; intervening on L moves S; if it does not, E<n> is wrong'>"
## Evidence that grades it
- Behavioral: on the subset the agent will <do X instead of Y> — visible in trace turns / tool-call outputs
- Aggregate (de-noised): the subset's mean stable-pass / score rises by ≥<k>; ≤<m> currently-stable tasks regress (the class designed not to hurt, and why)
## Aggregate bet (machine) — parsed and graded mechanically; keep the exact format
- subset: <task_id, task_id, ...>   ← a gain bet draws its subset from `gradient` (and, when buying information, `unknown`) tasks; `ceiling`/`env`/`noise` tasks do not belong in a subset you expect to move
- min_mean_delta: <float — the predicted rise in the subset's stable pass-rate, e.g. 0.10>
- max_stable_regressions: <int — run-wide stable pass→fail flips this change may cost>
## Falsification
<which behavioral OR aggregate outcome, if it does NOT happen, refutes the claim and lowers E<n>>
```

## Invariants (every round)

- Within a *single iteration*, a failed bet that **updates the model** is still
  a SUCCESSFUL calibration step — never reward-hack or overfit to salvage one
  iteration's score.
- Bet the ENVIRONMENT's behavior on a subset, never which individual tasks
  flip: single-task pass/fail sits below the noise floor and grades ~random.
  (Stable-vs-unstable is defined under the Aggregate axis above.)
- The runtime **code stays general**: a prediction may name tasks, but the agent
  code may never branch on a `task_id` or embed an answer.
