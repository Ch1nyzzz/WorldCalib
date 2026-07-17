---
name: worldcalib-proposer-spider2
description: Optimizer1 proposer skill for the Spider2 text-to-SQL agent policy. Runs one optimization iteration — self-distill the last prediction, design one mechanism-level change to the single-shot SQL-generation policy, write pending_eval.json. Self-distill WMC, no external critic.
---

# Optimizer1 proposer — Spider2 text-to-SQL agent policy (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the Spider2 agent's text-to-SQL
policy, and write a `pending_eval.json` describing that candidate. The outer loop
evaluates the candidate (real Spider2-lite local tasks, execution-match scored)
after this session exits.

<!-- INCLUDE: spider2/_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->

<!-- INCLUDE: agentic/_calib_addon.md -->

