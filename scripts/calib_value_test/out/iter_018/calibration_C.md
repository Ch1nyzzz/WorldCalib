# World Model Calibration

Append-only. The proposer must read this file before reasoning about the next
candidate, distill any mismatch from the previous iter, then append a new
`## iter_NNN distill` section. Never rewrite or delete prior entries.

## Observability

Each iter produces:
- a per-task answer score (passrate)
- per-task token consumption (prompt + completion)
- traces under `iter_NNN/workspace/traces/`
- failure type distribution recoverable from those traces

There is no hidden / shadow score and no judge that observes generalization.
Train passrate is therefore the only outcome dimension the proposer can predict
against. Do NOT write unfalsifiable generalization judgements into this file —
keep entries to outcome predictions and concrete mismatch observations.

