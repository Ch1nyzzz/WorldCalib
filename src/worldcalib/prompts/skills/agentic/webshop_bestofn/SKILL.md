---
name: worldcalib-proposer-agentic-webshop-bestofn
description: Optimizer1 proposer skill for the AgentBench WebShop agent policy. Runs one optimization iteration — self-distill the last prediction, design one mechanism-level change to the agent query strategy, write pending_eval.json. Self-distill WMC, no external critic.
---

# Optimizer1 proposer — AgentBench WebShop agent policy (best-of-N, external selector)

You run **one** iteration of an outer optimization loop: read the iteration's
evidence, design one mechanism-level change to the WebShop agent's runtime
policy, and write a `pending_eval.json` describing that candidate. The outer loop
evaluates the candidate (real AgentBench WebShop episodes) after this session
exits.

<!-- INCLUDE: agentic/_agentbench_surface.md -->

<!-- INCLUDE: agentic/_base_core.md -->

<!-- INCLUDE: agentic/_bestofn_addon.md -->

<!-- INCLUDE: agentic/_webshop_tail.md -->
