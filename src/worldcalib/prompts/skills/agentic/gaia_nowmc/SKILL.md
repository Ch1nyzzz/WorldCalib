---
name: worldcalib-proposer-agentic-gaia-nowmc
description: Pure-default (NO-WMC ablation) proposer skill for the GAIA agent policy. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the FC-loop agent policy, write pending_eval.json. No calibration protocol.
---

# Optimizer1 proposer — GAIA agent policy (no calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the GAIA agent's function-calling
policy, and write a `pending_eval.json` describing that candidate. The outer
loop evaluates the candidate (real GAIA episodes, exact-match scored) after this
session exits.

<!-- INCLUDE: agentic/_gaia_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->

