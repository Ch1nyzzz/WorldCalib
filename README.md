# WorldCalib

WorldCalib is the reference implementation for belief-calibrated scaffold
optimization. An outer proposer edits an agent or memory scaffold; the
calibrated arm maintains a persistent, falsifiable model of how the target
environment responds, while the matched `nowmc` arm sees the same evidence and
search surface without that persistent model.

This source release is aligned to the paper. It contains the five main
benchmarks—LongMemEval-s, LoCoMo, GAIA, AppWorld, and Terminal-Bench 2.0—and the
Toolathlon and Spider2-lite diagnostic implementations discussed in the
limitations. WebShop, OS, and unrelated internal experiments are intentionally
outside the release.

No experiment outputs, cached trajectories, model credentials, benchmark data,
or third-party checkouts are versioned.

## Install

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Install the GAIA readers and search integrations when needed:

```bash
pip install -e '.[gaia,dev]'
```

Copy `.env.example` to `.env`, add credentials locally, and configure external
benchmark roots. The CLI reads `.env` only from `--work-dir` (the current
directory by default); it never infers a repository root from package source
paths.

## Run

The public entry point has one positional benchmark and a shared optimization
interface:

```bash
worldcalib-optimize locomo \
  --run-id locomo-calib \
  --data-path /path/to/locomo10.json \
  --split-path /path/to/locomo-split.json \
  --iterations 30 \
  --proposer-variant calib
```

Use `--proposer-variant nowmc` for the matched no-world-model arm. Examples for
all benchmarks and the paired-run protocol are in
[docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

## Repository layout

```text
src/worldcalib/
  benchmarks/       benchmark-specific data, runners, and optimizers
  prompts/           calibrated and no-WMC proposer contracts
  runners/           benchmark-neutral external runner infrastructure
  traces/            normalized trace capture and optional semantic lookup
  optimizer.py       shared propose → evaluate → update loop
scripts/analysis/    paper-aligned offline belief-fidelity analysis
tests/               unit and release-integrity tests
docs/                benchmark, architecture, and reproduction notes
```

Frozen task identifiers live beside their loaders as package resources. Large
datasets and upstream systems stay outside the repository and are selected by
CLI arguments or environment variables. See
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Release invariants

- Runtime output belongs under `runs/`, `results/`, `logs/`, or `artifacts/`;
  all are ignored by Git.
- Candidate code may not branch on task IDs, inspect held-out answers, or call
  verifiers at inference time.
- Calibrated and no-WMC arms must share the same seed, target model, split,
  editable surface, evaluator, and iteration budget.
- External paths are explicit. Personal absolute paths and source-tree parent
  traversal are not part of the implementation.

Running agent benchmarks executes generated code and may invoke network,
container, browser, or shell tools. Read [SECURITY.md](SECURITY.md) before using
untrusted candidates or datasets.

## Development

```bash
python -m pytest -q
python -m build
```

The benchmark table and split invariants are covered by tests so accidental
scope drift is caught before release.
