---
name: worldcalib-proposer-agentic-db-tail
description: DB task tail — failure-mode bullets and the factual task-type-label granularity note. Shared by both the db_calib and db_nowmc arms.
---

## DB task-specific hints

The DB task asks the agent to answer questions or mutate rows by issuing SQL
against a provided schema. The `score_breakdown` task-type labels are the SQL
operation classes: `SELECT`, `counting`, `comparison`, `ranking`,
`aggregation-*`, `INSERT`, `UPDATE`, and `other` — these are the per-task-type
breakdown keys in `candidate_results/<id>.json`.

Classify recurring failure modes from the traces (input to a *general* fix,
never a lookup table):

- malformed SQL — syntax errors, wrong table/column names not present in the
  schema, missing quoting of string literals;
- wrong aggregation / grouping — counting or ranking with an incorrect
  `GROUP BY` / `ORDER BY`, off-by-one `LIMIT`, mishandling ties;
- answer-format mismatch — returning a query result in the wrong shape, or not
  committing the final answer in the expected format;
- mutation without verification — running `INSERT` / `UPDATE` then reporting
  success without reading back the affected rows;
- premature give-up — abandoning after one SQL error instead of reading the
  error and correcting the statement.
