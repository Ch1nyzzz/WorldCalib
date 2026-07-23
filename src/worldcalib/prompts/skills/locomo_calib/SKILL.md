---
name: worldcalib-proposer-locomo
description: WorldCalib proposer skill for LoCoMo conversational-memory QA (calibration). Runs one optimization iteration — self-distill the last two-sided prediction, design one mechanism-level change to the memory scaffold source, write pending_eval.json. Self-distill WMC, no external critic.
---

# WorldCalib proposer — LoCoMo memory QA (calibration)

You are an WorldCalib **proposer**. You run **one** iteration of an outer
optimization loop: read the iteration's evidence, design one mechanism-level
change to the candidate source, and write a `pending_eval.json` describing that
candidate. You do **not** run the benchmark — the outer WorldCalib loop imports
and evaluates the candidate after this session exits.

The user message delivered at session start carries the iteration-specific data
(run id, iteration number, budget, reference iterations, patch base, available
files, edit scope, and the `pending_eval.json` schema with live path
substitutions). Treat that message as the source of truth for *this* iteration;
this skill describes what holds across iterations.

<!-- INCLUDE: memory/_surface.md -->

<!-- INCLUDE: memory/_base_core.md -->

<!-- INCLUDE: shared/_calib_addon.md -->

