---
name: worldcalib-proposer-toolathlon-nowmc
description: Pure-default (NO-WMC ablation) proposer skill for the Toolathlon multi-app agent policy. Runs one optimization iteration — analyze evidence, design one mechanism-level change to the tool-use agent scaffold, write pending_eval.json. No calibration protocol.
---

# Optimizer1 proposer — Toolathlon agent policy (no calibration)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the Toolathlon agent's tool-use
scaffold, and write a `pending_eval.json` describing that candidate. The outer
loop evaluates the candidate (real Toolathlon finalpool tasks, end-state graded)
after this session exits.

<!-- INCLUDE: toolathlon/_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->
