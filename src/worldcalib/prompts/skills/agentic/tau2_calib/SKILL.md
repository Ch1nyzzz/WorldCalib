---
name: worldcalib-proposer-agentic-tau2
description: Optimizer1 proposer skill for the tau2 telecom agent policy. Runs one optimization iteration — self-distill the last two-sided prediction, design one mechanism-level change to the agent policy, write pending_eval.json. Self-distill WMC, no external critic.
---

# Optimizer1 proposer — tau2 telecom agent policy (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the tau2 telecom agent's runtime
policy, and write a `pending_eval.json` describing that candidate. The outer loop
evaluates the candidate (real tau2 episodes) after this session exits.

<!-- INCLUDE: agentic/_tau2_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->

<!-- INCLUDE: agentic/_calib_addon.md -->

<!-- INCLUDE: agentic/_tau2_tail.md -->
