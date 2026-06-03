---
name: worldcalib-proposer-tau2-surface
description: tau2-specific evolving surface for the agentic proposer — the Tau2Scaffold.build_agent / LLMAgent subclass strategy, editable seed_passthrough/base paths, the tau2-specific hard rules (do not alter domain_policy; importing tau2.* is fine), and pending_eval conventions (kind="tau2_agent", scaffold_name="tau2_passthrough"). Spliced ahead of the shared calib core.
---

## What you are evolving

You are evolving the **agent policy** for tau2 — a dual-control benchmark where
the agent converses with a (simulated) user and acts on a stateful environment
via tool calls, scored on whether it reaches the task's goal state. Concretely
you evolve a `Tau2Scaffold` whose `build_agent(*, tools, domain_policy, llm,
llm_args) -> LLMAgent` builds the agent for each episode. The frozen LLM
(deepseek) underneath is fixed; you evolve the *strategy wrapped around it*.

The runtime candidate is the source-backed scaffold `tau2_passthrough`, loaded
from the edited snapshot. The editable surface:

- `src/worldcalib/agentic/backends/tau2/seed_passthrough.py` — the policy. The
  seed is a pure pass-through: `build_agent` returns tau2's stock `LLMAgent`.
  Override `build_agent` to return a smarter agent.
- `src/worldcalib/agentic/backends/tau2/base.py` — `Tau2Scaffold` base:
  `self.config` is the `ScaffoldConfig`; one fresh scaffold runs per episode, so
  per-episode state on `self` is safe.

The tau2 agent is driven by tau2's `Orchestrator`, NOT by an agentrl `query`
loop. The LLM call goes through tau2's `generate()` (litellm). So you add
strategy by returning a `tau2.agent.llm_agent.LLMAgent` **subclass**. Things you
can do (non-exhaustive — invent what the failure modes call for):

- override the agent's `system_prompt` property to layer extra
  instructions/strategy on top of the (fixed) domain `policy` — e.g. planning
  habits, verification before irreversible actions, when to ask the user vs. act,
  tool-use discipline, how to read back state.
- override `generate_next_message` / `_generate_next_message` to add reflection,
  retry on malformed tool calls, self-consistency, tool-call validation, or
  loop/stall detection across turns.
- reshape the message history the model sees, or augment tool descriptions.

You may **not** change the `domain_policy` text itself (it is part of the task
and is what the agent is graded against), nor the user simulator, nor the
evaluation. Layer strategy *around* the policy. **Do not assume any fixed layer
structure** — choose the mechanism that targets a real failure mode.

## tau2-specific hard rules

These are in addition to the generic Hard rules below:

- **Importing from `tau2.*` is fine** — tau2 is a stable installed package; only
  late imports of `worldcalib.*` inside method bodies are forbidden.
- **Do not alter the `domain_policy`** passed into `build_agent`, and do not
  re-implement or bypass the user simulator or evaluator. Strategy layers around
  the policy, never replaces it.

## pending_eval.json conventions

The exact output path and schema are in the iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- The candidate MUST set `"kind": "tau2_agent"` and `"scaffold_name": "tau2_passthrough"`.
- Point `extra.source_project_path` at the edited snapshot project source when
  you modify `project_source/src/worldcalib/agentic/backends/tau2/...`.
- `top_k` must be a single integer (unused by the agent; set to 1).
- The `hypothesis` field must state: expected passrate direction, the failure
  family targeted, at least two independent evidence sources, and one
  counterexample class the change was designed not to hurt.
