---
name: worldcalib-proposer-appworld
description: WorldCalib proposer skill for the AppWorld interactive coding agent. Runs one optimization iteration — self-distill the last prediction, design one mechanism-level change to the ReAct code agent, write pending_eval.json. Self-distill WMC, no external critic.
---

# WorldCalib proposer — AppWorld coding agent (calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the AppWorld agent's ReAct code
policy (`agent.py`), and write a `pending_eval.json` describing that candidate.
The outer loop evaluates the candidate (real AppWorld tasks, state-based unit
tests) after this session exits.

<!-- INCLUDE: appworld/_surface.md -->

<!-- INCLUDE: shared/_base_core.md -->

<!-- INCLUDE: shared/_calib_addon.md -->
