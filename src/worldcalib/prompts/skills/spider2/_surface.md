---
name: worldcalib-proposer-spider2-surface
description: Spider2 backend contract for the text-to-SQL proposer — what the editable backend snapshot contains, the evidence it may read while designing (the read-only databases at /spider2_db, each task's result_preview and gold_answer), the only hard constraints (target model LOCKED; scorer/data-loader OFF-LIMITS and absent by design; gold is evidence but must never be transmitted into the policy; the predicted SQL is executed), and the pending_eval output contract (kind="spider2_agent", scaffold_name="spider2_passthrough"). No failure-mode taxonomy and no mechanism suggestions: the proposer analyses all the feedback and patches the policy itself. Spliced ahead of the shared core.
---

## What you are evolving

You are evolving the **agent policy** for Spider2-lite — a real-world enterprise
text-to-SQL benchmark. Each task gives a natural-language question over one
database (an obfuscated business/analytics schema); the agent must produce ONE
SQL query whose **execution result table** matches the gold result. Scope here is
the **local sqlite subset** (the queries run against bundled SQLite DBs). The
frozen LLM underneath (deepseek-v4-flash) is the fixed SUT; you evolve the
scaffold wrapped around it.

The runtime candidate is the source-backed scaffold `spider2_passthrough`, loaded
from the edited snapshot. The editable surface is the spider2 backend source tree
under `project_source/src/worldcalib/agentic/backends/spider2/**`:

- `seed_passthrough.py` — **the policy** (primary). The seed is a single
  generation: a `SYSTEM_PROMPT`, one `chat(...)` call built from the task's
  schema + external knowledge + question, then `extract_sql` pulls the ```sql
  block.
- `llm.py` — the chat client (retry/limit behavior; but see the hard rules — the
  model is locked).

You may edit any file in that tree **and add new files/modules** — the whole
snapshot propagates to the eval run, so new modules are importable. Anything in
that surface is policy you may rewrite however the evidence directs — there is no
prescribed lever or failure mode; read the source and the feedback and decide.

`solve_task` receives a gold-free task view: `{"instance_id", "db", "question",
"external_knowledge", "schema", "db_path"}` — where `schema` is the DB's
`CREATE TABLE` DDL and `db_path` is an absolute, **read-only** path to the sqlite
file. It must return `{"sql", "prompt_tokens", "completion_tokens", "error"}`.

## Evidence you can read while designing

- **The databases are mounted read-only at `/spider2_db/<db>.sqlite`.** Query them
  yourself, with `sqlite3`. The gold result CSVs are not mounted, so nothing there
  is an answer. The DDL names a column; it does not tell you what is in it.
- **`result_preview` on each task's outcome record is what that candidate's own SQL
  returned** — row count plus a capped head of the rows. `grade_error` reports only
  THAT grading failed.
- **`gold_answer` is the result table the query was graded against**, including every
  accepted variant. Read it alongside `result_preview`; neither is legible alone.
- **Never let gold cross into the policy.** Reading it to diagnose is the point;
  writing it — or anything derived per-instance from it — into the scaffold is
  reward-hacking and is rejected. Rules you infer must hold for tasks you have never
  seen, not just for the ones whose gold you just read.

Diagnose from these, not from re-reading the query. If the evidence for a claim is
not in front of you, say the evidence is missing — do not promote a guess about the
cause into a hypothesis.

## Hard constraints (the only fences)

These are in addition to the generic Hard rules below:

- **The target model is LOCKED to deepseek-v4-flash.** `chat()` raises if any
  caller passes a different `model`. Never change `MODEL_NAME`, never pass a
  `model=` override, never add a second model.
- **OFF-LIMITS — never edit, re-implement, or bypass** the scorer or the data
  loader. The execution-match `scorer.py`, `evaluation.py` and `data.py` (which hold
  the split and the grading semantics) are NOT in your workspace by design — do not
  recreate them and do not try to influence how you are scored.
- **Gold is evidence, not an answer key.** Each outcome record carries that task's
  `gold_answer`, and reading it to diagnose is expected and correct. What is
  rejected is **transmitting** it into the policy: never branch on `instance_id`,
  never embed a hand-written answer, and never encode a rule that holds only for the
  tasks whose gold you have seen. The scaffold is scored on tasks you will never
  see — a change that cannot generalise is reward-hacking even when it is dressed as
  a general rule.
- **The predicted SQL is EXECUTED.** It runs against a real sqlite DB and the
  result table is compared to gold (column-subset match, order-insensitive unless
  the gold requires order). A query that errors, returns the wrong columns, or
  wraps the answer in extra columns scores **0**.
- **One statement.** Return a single SQL query (SQLite dialect). The extractor
  takes the ```sql block; multiple statements or trailing prose break grading.

## pending_eval.json contract

The exact output path and schema are in the iteration message. Independent of those:

- The `candidates` array must contain exactly one candidate.
- The candidate MUST set `"kind": "spider2_agent"` and `"scaffold_name": "spider2_passthrough"`.
- Point `extra.source_project_path` at the edited snapshot project source when
  you modify `project_source/src/worldcalib/agentic/backends/spider2/...`.
- `top_k` must be a single integer (set to 1).
- The `hypothesis` field: the change you made, the expected `passrate` direction,
  and the evidence it came from.
