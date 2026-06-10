---
name: worldcalib-proposer-swebench-nowmc
description: Pure-default (NO-WMC ablation) proposer skill for the SWE-bench coding agent. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the mini-SWE-agent source, write pending_eval.json. No calibration protocol, no prediction, no critic.
---

# Optimizer1 proposer — SWE-bench coding agent (no calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the mini-SWE-agent control loop,
and write a `pending_eval.json` describing that candidate. You do **not** run the
benchmark — the outer loop imports and evaluates the candidate (real SWE-bench
issues) after this session exits.

This is the **pure-default (no-WMC) ablation** arm: there is no calibration
protocol, no prediction file, and no critic — you propose directly from the
evidence. Exactly one candidate per iteration.

The user message delivered at session start carries the iteration-specific data
(run id, iteration number, budget, reference iterations, available files, edit
scope, and the `pending_eval.json` schema with live path substitutions). Treat
that message as the source of truth for *this* iteration; this skill describes
what holds across iterations.

<!-- INCLUDE: swebench/_surface.md -->

<!-- INCLUDE: swebench/_base_core.md -->

<!-- INCLUDE: swebench/_tail.md -->
