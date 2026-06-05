---
name: worldcalib-proposer-swebench-calib
description: Self-distill world-model-calibration (single-proposer WMC, NO external critic, NO fan-out, NO best-of-N) proposer skill for the SWE-bench coding agent. Runs one optimization iteration — self-distill the last prediction, triage every currently-failing issue one by one, design one mechanism-level change to the mini-SWE-agent source, write prediction.md and pending_eval.json.
---

# Optimizer1 proposer — SWE-bench coding agent (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the mini-SWE-agent control loop,
and write a `pending_eval.json` describing that candidate. You do **not** run the
benchmark — the outer loop imports and evaluates the candidate (real SWE-bench
issues) after this session exits.

This is the **single-proposer self-distill WMC** arm: you maintain and self-grade
a two-sided per-issue prediction each iteration. There is no external critic, no
fan-out, and no best-of-N — exactly one candidate per iteration.

The user message delivered at session start carries the iteration-specific data
(run id, iteration number, budget, reference iterations, available files, edit
scope, and the `pending_eval.json` schema with live path substitutions). Treat
that message as the source of truth for *this* iteration; this skill describes
what holds across iterations.

<!-- INCLUDE: swebench/_surface.md -->

<!-- INCLUDE: swebench/_base_core.md -->

<!-- INCLUDE: swebench/_calib_addon.md -->

<!-- INCLUDE: swebench/_tail.md -->
