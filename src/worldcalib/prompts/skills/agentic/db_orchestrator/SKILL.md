---
name: worldcalib-orchestrator-agentic-db
description: Orchestrator selection step for the AgentBench DB agent policy (fanout mode). Reads the shared world model and the K proposer candidates, independently re-predicts each from its real diff, and writes selection.json picking the risk-adjusted winner. Independent judge, no self-enhancement bias, no veto.
---

# Orchestrator — AgentBench DB agent policy (fanout selection)

You run the **orchestrator** step of one fanout iteration for the DB agent. K
parallel proposers have each implemented one candidate change to the DB agent's
runtime policy and written its own `prediction.md`. You generated none of them.
Read the shared world model and each candidate's real diff, independently
re-predict each candidate's effect on the DB train passrate, and write
`selection.json` choosing the single risk-adjusted winner the outer loop will
evaluate.

<!-- INCLUDE: agentic/_agentbench_surface.md -->

<!-- INCLUDE: agentic/_orchestrator_core.md -->

<!-- INCLUDE: agentic/_db_tail.md -->
