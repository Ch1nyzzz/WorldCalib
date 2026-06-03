---
name: worldcalib-proposer-agentic-db-nowmc
description: Pure-default (NO-WMC ablation) proposer skill for the AgentBench DB agent policy. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the agent query strategy, write pending_eval.json. No calibration protocol.
---

# Optimizer1 proposer — AgentBench DB agent policy (no calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the DB agent's runtime policy, and
write a `pending_eval.json` describing that candidate. The outer loop evaluates
the candidate (real AgentBench DB episodes) after this session exits.

<!-- INCLUDE: agentic/_agentbench_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->

<!-- INCLUDE: agentic/_db_tail.md -->
