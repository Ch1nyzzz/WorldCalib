---
name: worldcalib-proposer-tb2-calib
description: Self-distill world-model-calibration (single-proposer WMC, NO external critic, NO fan-out, NO best-of-N) proposer skill for the Terminal-Bench 2.0 terminus-2 harness agent. Runs one optimization iteration — self-distill the last prediction, design one mechanism-level change to the terminus-2 harness, write prediction.md and pending_eval.json.
---

# Optimizer1 proposer — Terminal-Bench 2.0 terminus-2 harness (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the terminus-2 harness, and write a
`pending_eval.json` describing that candidate. You do **not** run the benchmark —
the outer loop evaluates the candidate (real Terminal-Bench 2.0 tasks, scored by
each task's own verifier) after this session exits.

The user message delivered at session start carries the iteration-specific data
(run id, iteration number, budget, reference iterations, available files, edit
scope, and the `pending_eval.json` schema with live path substitutions). Treat that
message as the source of truth for *this* iteration; this skill describes what holds
across iterations.

<!-- INCLUDE: tb2/_surface.md -->

<!-- INCLUDE: tb2/_base_core.md -->

<!-- INCLUDE: agentic/_calib_addon.md -->
