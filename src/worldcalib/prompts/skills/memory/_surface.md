---
name: worldcalib-proposer-memory-surface
description: Memory-specific evolving surface for the memory proposer — what the editable source surface contains (MemoryScaffold build()/answer() and the shared runtime helpers), and the pending_eval output contract (source-backed memgpt scaffold, build_tag for persisted-memory changes). The proposer analyses all the feedback and patches the scaffold itself. Spliced ahead of the shared base core; shared by both the calib and nowmc arms.
---

## What you are evolving

You are evolving a **memory layer** that answers questions over long
conversations. The runtime candidate is loaded through the source-backed
scaffold named in the iteration schema, typically `memgpt_source`. Memory
construction (`build()`) ingests the conversation into the memory store; answer
synthesis (`answer()`) recalls evidence and produces the final answer. The usual
source-backed surfaces:

- `src/worldcalib/benchmarks/memory/scaffolds/memgpt_scaffold.py` — memory construction, recall,
  archival search, retrieval, ranking, deduplication, and hit formatting.
- `src/worldcalib/model.py` — answer-message construction, system/user prompt
  shaping, context packing, and final-answer formatting.
- `src/worldcalib/scaffolds/base.py`, `src/worldcalib/source_base.py`,
  `src/worldcalib/dynamic.py`, `src/worldcalib/utils/**` — shared runtime
  interfaces and helpers when a mechanism genuinely needs them.

You may override or rewrite any function or method, restructure control flow,
change how the model is called, add or remove components, introduce new data
structures, or replace a mechanism wholesale — anything expressible in Python in
the editable surface is fair game.

## pending_eval.json conventions

The exact output path and JSON schema (with live substitutions) are in the
iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- `top_k` must be a single integer.
- Use a source-backed scaffold whenever you edit the copied scaffold source, and
  point `extra.source_project_path` at the edited snapshot project source when
  files under `project_source/src/worldcalib/` are modified.
- If you create a wrapper module under the generated directory, keep it small
  and route source-backed mechanisms through the clean edited snapshot.
- Source-backed baseline memories are read-only and expensive to rebuild. If your
  edit changes build/database-construction or other persisted
  memory-construction semantics, use a new stable `build_tag` and any required
  fresh source-base routing.
- `hypothesis`: the change you made, the expected `passrate` / `average_score`
  direction, and the evidence it came from.
