---
name: worldcalib-proposer-autolab-calib
description: Self-distill world-model-calibration (single-proposer WMC, NO external critic, NO fan-out, NO best-of-N) proposer skill for the AutoLab terminus-2 harness agent. Runs one optimization iteration — self-distill the last prediction, design one mechanism-level change to the terminus-2 harness, write a per-task pass↔fail prediction.md (each predicted flip carries a reason; no score deltas, no buckets) and pending_eval.json.
---

# Optimizer1 proposer — AutoLab terminus-2 harness (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the terminus-2 agent harness, and
write a `pending_eval.json` describing that candidate. You do **not** run the
benchmark — the outer loop runs the candidate harness against the AutoLab tasks
(via the harbor runner) and scores it into a continuous reward after this session
exits.

This is the **single-proposer self-distill WMC** arm: you maintain and self-grade
a per-task pass↔fail prediction each iteration (predict which tasks flip, each
with a reason — never a score). There is no external critic, no fan-out, and no
best-of-N — exactly one candidate per iteration.

The user message delivered at session start carries the iteration-specific data
(run id, iteration number, budget, reference iterations, available files, edit
scope, and the `pending_eval.json` schema with live path substitutions). Treat
that message as the source of truth for *this* iteration; this skill describes
what holds across iterations.

<!-- INCLUDE: autolab/_surface.md -->

<!-- INCLUDE: autolab/_base_core.md -->

<!-- INCLUDE: autolab/_calib_addon.md -->

<!-- INCLUDE: autolab/_tail.md -->
