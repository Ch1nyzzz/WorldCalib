# Architecture

WorldCalib separates the optimization protocol from benchmark execution.

1. A benchmark loader selects the frozen train or held-out tasks.
2. The shared optimizer evaluates a seed frontier or reuses a byte-identical
   baseline.
3. The proposer receives a benchmark-scoped source snapshot, normalized traces,
   score history, and—only in the calibrated arm—the persistent world model.
4. It writes one `pending_eval.json` candidate and one mechanism-level source
   change.
5. The benchmark runner evaluates that isolated candidate and emits the common
   `CandidateResult` plus per-task records.
6. Post-evaluation code normalizes evidence and updates the frontier. In the
   next iteration, the calibrated proposer grades its prediction and corrects
   its beliefs using raw evidence.

## Boundaries

- `optimizer.py` owns iteration state, proposer workspaces, lineage, and
  matched-arm mechanics.
- `benchmarks/<name>/` owns dataset interpretation and grading semantics.
- `benchmark_workspaces.py` declares exactly which installed package resources
  are copied into each editable snapshot.
- `runners/harbor.py` contains benchmark-neutral Harbor process supervision.
- `traces/` normalizes benchmark records and provides the independent
  `worldcalib-traces` semantic lookup service used by the proposer.
- `prompts/` loads package resources through `importlib.resources`; prompt
  selection has only `calib` and `nowmc` variants.

External benchmark repositories are inputs, not import-time assumptions.
Runtime paths come from configuration, environment variables, or the declared
work directory. Package-owned prompts, split files, and seed sources are loaded
as package resources.

## Persistent run state

The canonical state is file-based: JSON/JSONL summaries, source snapshots,
normalized traces, candidate results, and the optional calibration Markdown.
Generated state is confined to the run directory and is excluded from the
source release.
