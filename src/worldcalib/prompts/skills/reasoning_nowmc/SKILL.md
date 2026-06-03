---
name: worldcalib-proposer-reasoning-arc-nowmc
description: Pure-default (NO-WMC ablation) proposer skill for the ARC-AGI-2 single-shot reasoning solver. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the ARC solver, write pending_eval.json. No calibration protocol.
---

# Optimizer1 proposer — ARC-AGI-2 reasoning solver (no calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the ARC-AGI-2 solver's runtime
policy, and write a `pending_eval.json` describing that candidate. The outer loop
evaluates the candidate (real ARC-AGI-2 tasks) after this session exits.

<!-- INCLUDE: reasoning/_surface.md -->

<!-- INCLUDE: reasoning/_base_core.md -->

<!-- INCLUDE: reasoning/_tail.md -->
