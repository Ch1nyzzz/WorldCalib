---
name: worldcalib-proposer-reasoning-arc
description: Optimizer1 proposer skill for the ARC-AGI-2 single-shot reasoning solver. Runs one optimization iteration — self-distill the last two-sided prediction, design one mechanism-level change to the ARC solver, write pending_eval.json. Self-distill WMC, no external critic.
---

# Optimizer1 proposer — ARC-AGI-2 reasoning solver (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the ARC-AGI-2 solver's runtime
policy, and write a `pending_eval.json` describing that candidate. The outer loop
evaluates the candidate (real ARC-AGI-2 tasks) after this session exits.

<!-- INCLUDE: reasoning/_surface.md -->

<!-- INCLUDE: reasoning/_base_core.md -->

<!-- INCLUDE: reasoning/_calib_addon.md -->

<!-- INCLUDE: reasoning/_tail.md -->
