---
name: worldcalib-proposer-appworld-nowmc
description: Pure-default (NO-WMC ablation) proposer skill for the AppWorld interactive coding agent. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the ReAct code agent, write pending_eval.json. No calibration protocol.
---

# Optimizer1 proposer — AppWorld coding agent (no calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the AppWorld agent's ReAct code
policy (`agent.py`), and write a `pending_eval.json` describing that candidate.
The outer loop evaluates the candidate (real AppWorld tasks, state-based unit
tests) after this session exits.

<!-- INCLUDE: appworld/_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->
