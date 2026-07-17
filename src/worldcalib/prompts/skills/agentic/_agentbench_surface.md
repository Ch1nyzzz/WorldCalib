---
name: worldcalib-proposer-agentbench-surface
description: AgentBench-specific evolving surface for the agentic proposer — the agentrl BaseClient query strategy, the editable seed_passthrough/base paths, the message/tool object contract (locked model; exceptions zero the run), and pending_eval conventions (kind="agent", scaffold_name="agent_passthrough"). No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and patches the scaffold itself. Spliced ahead of the shared calib core.
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

## Message & tool object contract — READ THIS BEFORE TOUCHING messages/tools

`messages` and `tools` are **not** attribute objects. Each `MessageRecord` /
`FunctionDefinition` is a thin `Convertible(content)` wrapper around a raw
provider-format payload — there is **no** `.role`, `.tool_calls`, `.name`, or
`.description` attribute, and the constructor takes a single positional
`content`, not keyword fields. Guessing the API silently breaks every episode:
any exception your `query` raises is swallowed by the eval harness and scored 0
(status `model error`), so a wrong call zeroes the whole run with no traceback.

Use the conversion API (verified against `agentrl.eval.convert`):

```python
from agentrl.eval.convert import (
    MessageRecord,
    FunctionDefinition,
    OpenAIChatCompletionInputMessageRecord,   # to build NEW messages
    OpenAIChatCompletionFunctionDefinition,   # to build NEW/edited tools
)

# READ history as plain OpenAI-format dicts (flattened list):
plain = MessageRecord.convert_all(messages, to="openai_chat_completion_input")
last = plain[-1]
role = last["role"]                      # NOT getattr(m, "role")
tool_calls = last.get("tool_calls")      # list of {"id", "type", "function": {"name","arguments"}}
tcid = last.get("tool_call_id")

# READ tools as plain dicts:
tdicts = FunctionDefinition.convert_all(tools, to="openai_chat_completion")
# each: {"type": "function", "function": {"name", "description", "parameters"}}

# BUILD a new input message (system / user / tool) — wrap a LIST of dicts:
sys_msg  = OpenAIChatCompletionInputMessageRecord([{"role": "system", "content": "..."}])
tool_msg = OpenAIChatCompletionInputMessageRecord(
    [{"role": "tool", "content": "...", "tool_call_id": tcid}]
)

# BUILD an edited tool:
new_tool = OpenAIChatCompletionFunctionDefinition(
    {"type": "function", "function": {"name": "search", "description": "...", "parameters": {...}}}
)
```

`query` must return `list[MessageRecord]`. The default body
`return await self.inner.query(messages, tools=tools, cache_key=cache_key)` works
because it forwards the opaque records untouched. When you build new
`*MessageRecord` objects, keep the originals as-is (only convert when you need to
*read* them). Never return bare dicts and never reconstruct an existing record
from its converted dict (let the originals pass through). One fresh instance runs
per episode, so counters / state on `self` are safe.

## pending_eval.json conventions

The exact output path and schema are in the iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- The candidate MUST set `"kind": "agent"` and `"scaffold_name": "agent_passthrough"`.
- Point `extra.source_project_path` at the edited snapshot project source when
  you modify `project_source/src/worldcalib/agentic/backends/agentbench/...`.
- `top_k` must be a single integer (unused by the agent; set to 1).
- The `hypothesis` field must state: the change you made, the expected passrate
  direction, and the evidence it came from.
