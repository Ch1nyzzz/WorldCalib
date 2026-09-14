# Reproducibility

## Matched-arm protocol

For a calibrated/no-WMC comparison, hold constant the seed scaffold, target
model, proposer model, split, editable surface, evaluator, and horizon. Reuse a
single iteration-0 baseline:

```bash
worldcalib-optimize locomo \
  --run-id locomo-seed --iterations 0 --proposer-variant nowmc \
  --data-path /path/to/locomo10.json --split-path /path/to/splits.json

worldcalib-optimize locomo \
  --run-id locomo-calib --iterations 30 --proposer-variant calib \
  --baseline-dir runs/locomo-seed \
  --data-path /path/to/locomo10.json --split-path /path/to/splits.json

worldcalib-optimize locomo \
  --run-id locomo-nowmc --iterations 30 --proposer-variant nowmc \
  --baseline-dir runs/locomo-seed \
  --data-path /path/to/locomo10.json --split-path /path/to/splits.json
```

Use `--test-frontier` to evaluate on held-out. GAIA, AppWorld and TB2 select
the highest train score, breaking ties by earliest iteration. Memory benchmarks
evaluate three highest-train candidates; the paper reports the best held-out
score among them. That memory procedure uses held-out scores for selection.
A positive `--test-frontier-candidate-limit` explicitly overrides this rule.

For Kimi, set both `KIMI_API_KEY` and `KIMI_BASE_URL` to matching credentials
and a Claude-compatible endpoint. Explicit `--proposer-auth-token` and
`--proposer-base-url` take precedence. Missing Kimi configuration fails early.

## Paper defaults

- Target: DeepSeek-V4-Flash at temperature 0 for LongMemEval-s, LoCoMo, GAIA,
  AppWorld, Spider2-lite, and Toolathlon.
- Target: MiniMax-M3 for Terminal-Bench 2.0, with two attempts averaged per
  task.
- Proposer: Kimi-K2.6 for memory QA; Kimi-K2.7 for GAIA, AppWorld, and the two
  diagnostic agent runs; Codex GPT-5.6 at maximum effort for Terminal-Bench
  2.0.

Provider-specific model identifiers and endpoints may differ. Record the exact
resolved values with each run and never change them between matched arms.

## Benchmark examples

The first four commands use the paper horizons. The last two are usage examples
for the diagnostics, not full reproduction commands; they use five iterations.

```bash
worldcalib-optimize longmemeval --run-id lme-calib \
  --data-path /path/to/longmemeval_s_cleaned.json \
  --split-path /path/to/splits_s.json --iterations 30

worldcalib-optimize gaia --run-id gaia-calib --iterations 20

worldcalib-optimize appworld --run-id appworld-calib --iterations 10 \
  --appworld-root /path/to/appworld-data \
  --appworld-python /path/to/appworld-env/bin/python

worldcalib-optimize tb2 --run-id tb2-calib --iterations 10 \
  --tb2-tasks-path /path/to/tb2/tasks \
  --tb2-terminus2-source /path/to/terminus2-source

worldcalib-optimize spider2 --run-id spider2-diagnostic \
  --spider2-root /path/to/Spider2/spider2-lite

worldcalib-optimize toolathlon --run-id toolathlon-diagnostic \
  --toolathlon-root /path/to/Toolathlon
```

## Offline belief-fidelity analysis

The simplified two-arm diagnostic in `scripts/analysis/belief_fidelity.py`
requires input/output directories, Kimi credentials and a Docker image with
Claude Code installed:

```bash
python scripts/analysis/belief_fidelity.py \
  --run-dir runs/locomo-calib \
  --out-dir runs/_belief_fidelity/locomo-calib --sample 10
```

Ten candidates are a per-run example. The paper's full 40-candidate experiment
also requires the falsified-document arm, second judge, original candidate
manifests and aggregation; those are not bundled. See [provenance](PROTOCOL.md)
for limits of final-document leave-one-out. These metrics are offline only.

## Verification

```bash
python -m pytest -q
python -m worldcalib.optimize_cli --help
python -m build
```

Before publication, archive environment manifests and raw outputs separately;
do not add them to the source repository.
