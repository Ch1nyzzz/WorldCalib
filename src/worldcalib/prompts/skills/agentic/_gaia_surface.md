---
name: worldcalib-proposer-gaia-surface
description: GAIA-specific evolving surface for the agentic proposer — the GaiaScaffold.solve_task FC loop, the editable seed_passthrough/tools paths, the GAIA-specific hard rules (target model is LOCKED; never edit the scorer or data loader; tools hit the real network/subprocess; answer is exact-match), and pending_eval conventions (kind="gaia_agent", scaffold_name="gaia_passthrough"). No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and patches the scaffold itself. Spliced ahead of the shared calib core.
---

## What you are evolving

You are evolving the **agent policy** for GAIA — a general-assistant benchmark
where the agent answers a real-world question by calling tools (web_search,
url_fetch, file_read, python_exec) in a function-calling loop, and the answer is
graded by **exact match** against the gold answer. You evolve a `GaiaScaffold`
whose `solve_task(task) -> dict` runs the loop for one task. The frozen LLM
underneath (deepseek-v4-flash) is the fixed SUT; you evolve the *strategy and
toolbox wrapped around it*.

The runtime candidate is the source-backed scaffold `gaia_passthrough`, loaded
from the edited snapshot. The editable surface:

- `src/worldcalib/agentic/backends/gaia/seed_passthrough.py` — **the policy**
  (primary). The seed is a plain FC loop: a `SYSTEM_PROMPT`, up to
  `MAX_ITERATIONS` turns of `chat(...)` + tool dispatch, then
  `_extract_final_answer`.
- `src/worldcalib/agentic/backends/gaia/tools/*.py` — the four tools
  (web_search, url_fetch, file_read, python_exec). Tools must keep the same
  `SPEC`/`run(args)->str` contract and never raise.
- `src/worldcalib/agentic/backends/gaia/llm.py` — the chat client. You may tune
  retry/limit behavior, but see the hard rules: the **model is locked**.

`solve_task` receives a gold-free task view: `{"task_id", "level", "file_name",
"prompt"}`. It must return `{"answer", "prompt_tokens", "completion_tokens",
"iterations", "finish_reason", "error"}`.

## GAIA-specific hard rules

These are in addition to the generic Hard rules below:

- **The target model is LOCKED to deepseek-v4-flash.** `chat()` raises if any
  caller passes a different `model`. Never change `MODEL_NAME`, never pass a
  `model=` override, never add a second model. The SUT is fixed; you evolve the
  scaffold around it.
- **Never edit, re-implement, or bypass the scorer or the data loader.** The
  official exact-match `scorer.py` and `data.py` (which holds the gold answers)
  are NOT in your workspace by design — do not recreate them, do not read gold
  answers, do not branch on `task_id` to special-case an answer. That is
  reward-hacking and is rejected.
- **Tools hit the real world**: `web_search`/`url_fetch` make live network calls
  (DuckDuckGo by default — rate-limited and noisy), `python_exec` runs a real
  subprocess.
- **The answer is graded by exact match** against the gold answer.

## pending_eval.json conventions

The exact output path and schema are in the iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- The candidate MUST set `"kind": "gaia_agent"` and `"scaffold_name": "gaia_passthrough"`.
- Point `extra.source_project_path` at the edited snapshot project source when
  you modify `project_source/src/worldcalib/agentic/backends/gaia/...`.
- `top_k` must be a single integer (unused by the agent; set to 1).
- The `hypothesis` field must state: the change you made, the expected passrate
  direction, and the evidence it came from.
