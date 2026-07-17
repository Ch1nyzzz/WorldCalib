---
name: meta-harness-skill
description: Build and audit WorldCalib optimization code so the proposer can actually see what it is asked to diagnose — the question, the candidate's full rollout, the consequences, and gold. Use when writing or changing any evaluation runner, scorer, trace adapter, span builder, access policy, dump-evidence list, or proposer skill text — i.e. anything that decides what the optimizer is allowed to observe. Also use when a run reports "reasoning errors / no fixable cause / capability ceiling", because that is the exact symptom this skill exists to rule out first.
---

# Meta-harness: the optimizer must see what it is asked to diagnose

## The one invariant

> **Every failure the proposer is asked to diagnose must carry, in the workspace
> it can actually read, the evidence of WHY it failed — not merely THAT it failed.**

A score is not evidence. `passed=False`, `Result Error`, `evaluator_returncode=1`,
`resolved: 0` are all tallies. They say a thing went wrong. They never say what.

## Why this is a validity threat, not an inconvenience

**Every dropped consequence looks exactly like a reasoning error in the trace.**

A harness that discards consequences does not merely lose information — it
*manufactures* failures that appear uncaused, and those fake failures are
indistinguishable from a genuine model-capability ceiling. Any conclusion of the
form "the optimizer plateaued, therefore the remaining failures are a reasoning
ceiling" is **unsound** until the consequence tier is verified present. This has
already happened here: two multi-iteration studies (spider2, 20 iters; swebench,
14 iters) produced exactly that conclusion, and it was partly an artifact of our
own plumbing.

So: before you attribute a plateau to the model, prove the proposer could see.

## What the proposer must see — including gold

A trace is diagnosable only if it carries **all four**:

| | Why it is load-bearing |
|---|---|
| **The question** | Without it you cannot tell what the candidate was even trying to do. A proposer given only the candidate's SQL will reverse-engineer the question from the query and diagnose the wrong thing. |
| **The candidate's full rollout** | The actual output/trajectory — not a restatement of the score. `prediction="success"` and `prediction=f"reward={score}"` are the score wearing the rollout's name. |
| **The consequences** | Returned rows, test log, traceback, exit status, tool responses, and the shape of the world the candidate queried (schema, value vocabularies, cardinalities). |
| **Gold** | See below. |

### Gold is diagnostic evidence. Show it.

An earlier version of this skill said gold must never be visible. **That was wrong,
and the repo's own runs falsified it.** The correction matters, so keep the reasoning:

**Gold is what separates a format failure from a content failure — the single most
important discrimination in this codebase.** With gold, a real GAIA proposer wrote:

> `0383a3ee: prediction "rockhopper penguin" vs gold "Rockhopper penguin" — case difference`
> `2dfc4c37: predicted "3" vs gold "6" (wrong answer, not format)`
> `Trailing period stripping is risky if a gold answer actually ends with a period`

The first is fixable plumbing. The second is a genuine reasoning failure. **`passed=False`
gives you neither.** Note the third line: it *declined* a hack that would have overfit
observed gold. That is a proposer reasoning well, not cheating.

Do not repeat the mistake this skill originally made: claiming consequences alone
suffice. They do not, and the claim was checked and failed. A "no helmet" group
returning 2778 collisions is **not** self-evidently wrong — California really does
have ~2796 motorcycle collisions. It is only absurd once gold says the group has 1.
The root cause of that task was found *by comparing against gold*.

### The risk is transmission, not viewing

| | Verdict |
|---|---|
| Proposer **reads** gold to diagnose | **Legitimate. Required.** |
| Proposer **writes** gold into the scaffold (`if instance_id == X: return <gold>`) | The actual failure mode. |

Transmission is already governed by three independent defences: the reward-hacking
ban in the proposer skills, the `reward_hack_attempt` detector, and the held-out
split. **Empirically it does not happen**: across 21 GAIA iterations with gold fully
visible, train passrate oscillated 0.325–0.550, never trended to 1.0, and the
detector fired zero times. Gold access is also **symmetric across arms**, so an A/B
comparison is not confounded by it.

So: show gold, ban transmission, keep the detector honest.

### The requirement that actually binds: coherence

The real defect is not leakage — it is that **no policy was ever written down**, so
each backend grew its own by accident:

```
GAIA     question=task_id      gold_answer=gold           ← hides the question, hands over the answer
spider2  question=<real text>  gold_answer=""             ← question yes, gold no
swebench question=<issue>      gold_answer="tests pass"   ← question yes, gold a placeholder
```

Three backends, three incompatible policies, none justified anywhere. GAIA's is the
absurd one: **it tells you the answer is "2" while withholding the question**, so
"2" is worthless — which is a live hypothesis for why GAIA sat at 0.400 → 0.400 for
20 iterations with the strongest possible signal in hand.

**A new backend must state its question/rollout/gold policy explicitly and match the
others, or document why it differs.** Nine accidents is not a design.

## The four ways evidence goes missing

Check for each by name. They are not hypothetical — each was found in this repo.

1. **Never captured.** The field is simply not on the record.
   *Example:* `TaskResult.question = instance_id` — the proposer could not read the
   question and reverse-engineered the task from the candidate's SQL.
2. **Computed, then destroyed.** The data is materialized and thrown away.
   *Example:* `score_sql` passed `result_csv_dir=None` and ran inside a
   `TemporaryDirectory`. The predicted rows were written to CSV, read into pandas,
   compared, and deleted — 20 times. **No permission fixes this. The bytes are gone.**
3. **Written to disk, never plumbed.** It exists; nothing carries it across.
   *Example:* 481 `test_output.txt` files from the SWE-bench harness, landing in
   `logs/run_evaluation/` — outside `--report_dir`, outside the task dir, never read.
4. **Asymmetric gating.** Evidence attaches to one failure class and not another.
   *Example:* `error_tail` was set only when `exit_status != "Submitted"` — i.e.
   only for harness self-destructs. The consequence was pathological: **the only
   failures carrying evidence were the harness's own bugs, so the proposer spent
   its entire diagnostic budget reverse-engineering the harness plumbing**
   (`grep PYTHONPATH`, `grep project_root`, `grep _PATCH_CREATION_RE`). It was not
   confused. It was going where the light was.

Note that only #3 is partly a permissions problem. **"Do they have permission?" is
the wrong first question** — it covers one of four causes.

## Checklist — writing or changing harness code

Before you land any change to an evaluation runner, scorer, adapter, span builder,
access policy, dump list, or proposer skill text:

- [ ] **Enumerate the failure modes** this benchmark actually produces. For each,
      answer literally: *"If I had to diagnose this myself, what file would I open?"*
      If that artifact is not in the proposer's readable workspace, **that is the bug** —
      fix it before touching prompts or search strategy.
- [ ] **Symmetry.** Every failure class carries evidence, not just the crash path.
      Grep your own `if` conditions around evidence attachment.
- [ ] **No silent drops.** Truncate at the source with an explicit marker; never let
      a size cap *skip* a file. A skipped file reads downstream as "nothing to see".
- [ ] **Read the record you produce**, not the one you intended. Open a real span for
      a real failing task and check each field is the thing its name promises.
      (`"question": "local015"`, `"gold": "tests pass"`, `"prediction": "patch: <path> (2336 bytes)"`
      all shipped and looked fine in code review.)
- [ ] **Pointers must be dereferenceable.** Do not hand the proposer a `patch_path` /
      `task_dir` / `db_path` that resolves into a forbidden root or an unmounted host
      path. A pointer it cannot follow is worse than no pointer: it reads as evidence.
- [ ] **All four present?** question, full rollout, consequences, gold — for a real
      failing task, in the workspace, checked by opening it. Missing any one of them
      makes the other three much weaker: gold without the question is worthless
      (ask GAIA), and consequences without gold cannot separate format from content.
- [ ] **Policy stated, not inherited.** Write down this backend's question / rollout /
      gold decision and make it match the other backends, or say why it differs.
- [ ] **Firewall by information, not by path.** `forbidden_roots: [project_root]` is a
      path rule; the world's data and the scoring machinery live in the same tree, so
      it cannot separate them. Carve the allow narrowly (`resource/databases/` yes,
      the scorer implementation no). Per-task gold for tasks already evaluated is
      evidence and rides the trace; a mount granting the entire gold corpus up front
      is a different thing and needs a reason.
- [ ] **Enforcement ≠ documentation.** Here the real boundary is the **Docker mount**
      (`proposer_docker_mount`); `access_policy.json` is advisory text for the model.
      Granting read access means adding a `:ro` mount, not editing a string.
- [ ] **Skill text must not overpromise.** If a skill says "read X for the verdict —
      it is all white-box", open X and confirm it contains a verdict. Ours pointed at
      a 408-byte tally that said `resolved: 0`. The proposer obeyed the instruction and
      found an empty box; its diagnosis then read `maybe … might … Need know`.

## A/B protocol: both arms start from a byte-identical iter0

Never let the two arms compute their own iter-0. Build the seed **once**, then run
both arms from it (`ITERATIONS=0 launch_<bench>.sh nowmc` → `SEED_FROM=runs/<seed>`
for each arm). Otherwise the arms diverge at step 0 from sampling noise alone, and
that noise is inside every gap you go on to measure — on a 31-task split one flipped
task is ±0.03, which is the size of the effects being claimed.

**Verify the sharing actually happened; do not assume it.** The mechanism is
silently broken in at least one backend (autolab's shared-iter0 hook needs a
`run_summary.json` the optimizer never writes, so the arms quietly seed themselves).
A silent fallback to independent seeds looks exactly like a successful share. One
command settles it:

```sh
md5sum runs/<seed>/candidate_results/iter000*.json \
       runs/<arm_a>/candidate_results/iter000*.json \
       runs/<arm_b>/candidate_results/iter000*.json   # three identical hashes, or stop
```

Same rule for anything else meant to be held constant across arms — the SUT model
and endpoint especially. When you re-point a SUT at a different endpoint, check the
seed passrate against the previous run's before reading anything into the arms: an
unchanged seed score is the evidence that the swap did not move the SUT. And never
change the SUT in the same run as a harness change — "the proposer can now see" and
"a stronger model solves more" are then indistinguishable, which is the confound
this whole skill is about, wearing a different hat.

## The tell

**A diagnosis written in hedges — "maybe", "likely", "could be", "Need know" — is
almost never a hard problem. It is missing evidence.**

When you see the proposer speculating about a cause, or reasoning about a program's
*text* rather than its *behavior*, do not tune the prompt and do not conclude
"capability ceiling". Find what it could not see.

Corollary for reporting: if the evidence for a claim is absent, the honest output is
"the evidence is missing", never a plausible guess promoted to a hypothesis. Say so
in the proposer skill too.

## Ordering

Fixes that restore evidence are **cheap and unarguable** — the candidate's own
output belongs to the candidate, and gold is governed by the hack ban + detector +
held-out rather than by hiding it. Do them first, before any prompt tuning.

Do not run an A/B, tune a prompt, or write up a ceiling result until you have opened
a real failing task's record and confirmed all four are there. Otherwise you are
measuring your own plumbing.

## A note on this skill's own history

The first version of this skill asserted a clean rule — "consequences yes, gold
never" — that was elegant, felt principled, and was **false**. It was falsified in
under a day by reading two artifacts: a proposer's reasoning (which used gold
correctly, to split format from content, and declined a gold-overfitting hack) and a
score table (21 iterations, gold fully visible, no memorisation, detector silent).

The lesson generalises past gold: **when this skill and the run records disagree,
the records win.** Check the claim against a real artifact before you act on it —
including the claims written here.
