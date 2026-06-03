---
name: worldcalib-proposer-agentbench-surface
description: AgentBench-specific evolving surface for the agentic proposer — the agentrl BaseClient query strategy, editable seed_passthrough/base paths, and pending_eval conventions (kind="agent", scaffold_name="agent_passthrough"). Spliced ahead of the shared calib core.
---

## What you are evolving

You are evolving the **agent policy** — an agentrl `BaseClient` subclass whose
`async query(messages, tools, cache_key) -> messages` decides, given the current
conversation and the available tools, the next assistant action (the model's
reply, including `tool_calls`). The frozen LLM (deepseek) underneath is fixed;
you evolve the *strategy wrapped around it*.

The runtime candidate is the source-backed scaffold `agent_passthrough`, loaded
from the edited snapshot. The editable surface:

- `src/worldcalib/agentic/backends/agentbench/seed_passthrough.py` — the policy.
  The seed is a pure pass-through (forwards messages+tools to the model
  unchanged). Override `query` to add strategy.
- `src/worldcalib/agentic/backends/agentbench/base.py` — `AgentScaffold` base:
  `self.inner` is the bound deepseek client (call `await self.inner.query(
  messages, tools=..., cache_key=...)`); `self.config` is the `ScaffoldConfig`;
  one fresh instance runs per episode, so per-episode state on `self` is safe.

Things you can do in `query` (non-exhaustive — invent what the failure modes
call for): reshape / compress / rewrite the message history before the model
sees it; augment `tools` (embed environment constraints into descriptions);
repair or validate the model's `tool_calls` before they are returned; add
reflection / retry / self-consistency; detect repetition / loops / stalls across
turns and steer; maintain cross-turn state. **Do not assume any fixed layer
structure** — choose the mechanism that targets a real failure mode.

## pending_eval.json conventions

The exact output path and schema are in the iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- The candidate MUST set `"kind": "agent"` and `"scaffold_name": "agent_passthrough"`.
- Point `extra.source_project_path` at the edited snapshot project source when
  you modify `project_source/src/worldcalib/agentic/backends/agentbench/...`.
- `top_k` must be a single integer (unused by the agent; set to 1).
- The `hypothesis` field must state: expected passrate direction, the failure
  family targeted, at least two independent evidence sources, and one
  counterexample class the change was designed not to hurt.
