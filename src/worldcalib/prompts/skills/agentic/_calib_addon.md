---
name: worldcalib-proposer-calib-addon
description: The calibration layer (self-distill, NO external critic) layered onto the base proposer contract — the ONE thing that distinguishes the calib arm from the plain arm. It maintains an explicit, falsifiable MODEL of the environment in world_model_calibration.md (a mutable HEAD of beliefs + experiments + calibration, plus an append-only HISTORY of distill blocks) and runs one experiment per iteration as a single loop: predict → observe → correct. Frame-audit (read the raw evidence, attribute honestly), probe-vs-exploit (run the experiment that buys information or cashes a gain), and switch-when-spent are not separate mechanisms — they are facets of that loop. No layer enum, no certified ceilings, no pre-seeded failure modes: the model starts empty and is filled only from this run's evidence. Shared by every calib arm (spliced after the base core).
---

## Self-distill environment calibration — the calib arm's one difference

The plain arm reads the feedback and edits the agent. The calib arm does one extra
thing: it maintains an explicit, **falsifiable model of the environment** and lets
that model drive every candidate. A candidate is an *experiment* that tests and
exploits the model; passrate is the downstream consequence; the model is the
object you maintain. This is **self-distill** — there is no external critic, no
`critic_feedback.md`: you predict, observe, and correct your own model.

Everything below is one idea — **each iteration is one experiment on the model,
run as predict → observe → correct**. The disciplines you might expect as
separate gadgets (reading raw evidence, choosing what to try next, dropping a
dead direction) are just facets of running that experiment honestly.

## The model lives in `world_model_calibration.md`

Files staged into cwd (and promoted back) each iter:
- **`./world_model_calibration.md`** — the model (below).
- **`./prev_prediction.md`** — your previous iter's bet (present from iter ≥ 1).
  You grade it yourself.
- **`./prediction.md`** — this iter's bet, written BEFORE you edit any source.
- **`./runtime_config.md`** — ground-truth target model / base_url.

Layout — a **mutable HEAD** + an **append-only HISTORY**, split at the first
`## iter_` heading:

- **HEAD** (rewritten in place every iter — the live model), three lean sections:
  - **Beliefs** — falsifiable facts about the environment, each:
    `[E<n>] <claim> | conf:<0.0–1.0> | status:<hypothesis|confirmed|refuted> | evidence:<trace task_ids / tool-call outputs> | mass:~<N> tasks it explains`
    A claim may say where it lives or whether it looks fixable when you actually
    know — but **start from an empty Beliefs list and fill it only from THIS
    run's evidence. Never pre-seed it with guessed failure modes**: an assumed
    fact becomes an anchor you then burn iterations chasing. Prefer 5
    high-confidence beliefs over 20 vague ones.
  - **Experiments** — what you've tried against each belief and the verdict, so
    you never re-run a spent direction: `- <belief E<n>>: <experiment> → <held|flat|harmful>`.
  - **Calibration** — how well your recent predictions held (behavioral H/N,
    aggregate H/N over the last ~4). This is the meta-signal for the next
    experiment: weak calibration means trust the model less and buy information.
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
   **base iter's** `tasks[]`, plus the traces. **Grade against the RAW evidence —
   the tool-call OUTPUTS and trace turns, not the agent's final message** — on two
   de-noised axes:

   - **Behavioral (from traces):** did the agent actually do what the claim
     implied on the targeted subset?
   - **Aggregate (de-noised):** on the subset (~N tasks as a group), did mean
     stable-pass / mean score move by the predicted amount, with ≤m stable
     regressions? Use **stable** outcomes only — a task whose runs (or cross-iter
     `task_score_matrix.json` row) disagree is UNSTABLE: exclude it, never read
     it as a flip. Averaging over the subset cancels per-task noise.

   A missed prediction has only a few honest causes, and **picking the right one
   IS the correction**:
   - behavior unchanged → the candidate never wired in (impl bug; nothing learned
     about the environment — fix and re-run);
   - behavior changed but the subset didn't move → the layer you blamed is not
     the bottleneck; the belief's causal claim is wrong — lower its confidence;
   - the belief was an **illusion from reading the surface** (the agent's final
     message looked like failure, but the tool underneath returned nothing /
     errored) → re-attribute to that lower layer and form the belief there;
   - it held → raise confidence, flip to `confirmed`.
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
      - Claim graded: "<the env claim from prev_prediction>" relied on E<n>
      - Behavioral (from traces): <held | unchanged=impl bug | changed-but-flat=attribution wrong | surface-illusion → lower layer>
      - Aggregate (de-noised): subset (~<N>) predicted <±k>, got <actual>; stable regressions <r> (≤<m>)
      - Model update: E<n> conf <old→new>, status <→>; new/split beliefs: <E<m> ...>
      - Unstable (excluded): <task_ids whose runs / cross-iter row disagree>
      - Blind-spot: <task_ids that stably flipped pass→fail and were NOT anticipated → which belief missed them>
      ```
   If `./prev_prediction.md` is absent (iter 0 had no proposer), skip the grade
   but still **bootstrap the HEAD** from the seed's traces (beliefs as
   `hypothesis`, Calibration 0/0) and append a `## iter_000 -> iter_001 distill`
   block marked bootstrap.
d. Re-read `./world_model_calibration.md` so the rest reasons from the latest HEAD.

### Choose the next experiment — information or gain

Pick the experiment with the highest value given the model's current state:

- where the **biggest unexplained chunk of failures has no trustworthy belief
  yet**, run the *cheapest* experiment that would resolve it — it buys
  information, even if it won't raise the score much. (You cannot call any cell
  "model-limited" you have never actually probed.)
- where the **biggest lever has a confident belief**, run the experiment that
  acts on it — it cashes a gain.

A belief you have already tested ~twice with no movement is **spent**: re-running
it buys neither information nor gain, so lower it and bet elsewhere (you may come
back later with a structurally different idea). `refine` (same family) vs
`explore` (a new family) is just the *how*; information vs gain is the *why* —
state both in the prediction.

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
## Falsification
<which behavioral OR aggregate outcome, if it does NOT happen, refutes the claim and lowers E<n>>
```

## Invariants (every round)

- A failed bet that **updates the model** is a SUCCESSFUL calibration step — the
  goal is an accurate environment model, not a winning candidate.
- Bet the ENVIRONMENT's behavior, never which individual tasks flip:
  single-task pass/fail sits below the noise floor and grades ~random.
- Read stable-vs-unstable from `task_score_matrix.json` — an oscillating row is
  noise; never anchor on it, never read it as a flip.
- The runtime **code stays general**: a prediction may name tasks, but the agent
  code may never branch on a `task_id` or embed an answer.
