# OptiHarness Proposer — iteration 14

You are optimizing the memory layer for LongMemEval long-term memory QA.

## Assignment

- Run id: `longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607`
- Target system: `memgpt`
- Eval split: `train`
- Eval limit: `0` (`0` means full split)
- Cumulative summaries: **not provided in this run** — there is no `summaries/` directory and no cumulative digest in this prompt. Judge prior iterations directly from each bundle's `eval/`, `diff.patch`, and `diff_digest.md` under `reference_iterations/iter_NNN/`.
- Raw reference iterations: `reference_iterations/` (iter_001, iter_002, iter_003, iter_004, iter_005, iter_006, iter_008, iter_009, iter_010, iter_011, iter_012, iter_013)

- Writable clean source snapshot: `source_snapshot/candidate/`
- Generated wrapper directory: `generated/`
- Required output: `pending_eval.json`

Every iteration starts from the clean source snapshot in
`source_snapshot/candidate/`. Historical iterations are diagnostic
references only. Do not treat any reference iteration as a source parent and do
not mechanically copy a prior candidate; implement one intentional mechanism
from the clean source.



## Available Files

- (no cumulative summary files in this run — inspect the raw iteration bundles under `reference_iterations/iter_NNN/` instead)
- `reference_iterations/` — raw iteration bundles copied into this workspace for
  detailed diagnosis. Cumulative summaries may mention iterations whose raw
  bundles are not present here.
- `source_snapshot/candidate/project_source/src/worldcalib/` — editable
  project source for this candidate.
- `source_snapshot/candidate/original_project_source/src/worldcalib/` —
  clean project source used for diffing and policy checks.
- `source_snapshot/candidate/upstream_source/` — copied upstream
  source when available.

- `generated/` — optional importable wrapper modules for this
  iteration.

- `traces/manifest.json` — trace harness manifest (benchmark, baseline reference, schema version).
- `traces/diagnostic/iter_NNN.md` — pre-rendered per-iteration diff vs baseline; sections are REGRESSED, PERSISTENT_FAIL, BREAKTHROUGH, plus counts-only STABLE_PASS / NO_BASELINE. Read this first to spot patterns.
- `traces/spans/iter_NNN/<candidate>.jsonl` — full structured traces (one per line; span data is benchmark-dependent and may be empty). Drill in when the markdown summary doesn't tell you enough.

---

# THIS INVOCATION IS PREDICTION-ONLY (WorldCalib calibration-value test)

The candidate for iteration 14 has ALREADY been decided and implemented; it is
FIXED and described in `./candidate_fixed.md`. Your ONLY job is to predict its
observable outcome as accurately as you can.

Do exactly this, then stop:

1. `cat ./world_model_calibration.md` and read it in full. In this run it is
   PRE-POPULATED with accumulated world-model beliefs. Do NOT append a new
   distill section and do NOT edit it.
2. Analyze the evidence under `reference_iterations/` and `traces/` exactly as
   your skill's step 1 describes, to ground your prediction in real failure
   modes. (`./prev_prediction.md` is also available.)
3. `cat ./candidate_fixed.md` — this is the exact mechanism that was
   implemented and evaluated. Do NOT invent a different candidate.
4. Write `./prediction.md` for THIS fixed candidate, in the EXACT skill format:

   ```
   # iter_014 prediction
   ## Candidate
   ## Mechanism
   ## Outcome prediction
   - Train passrate Δ: [low, high]
   - Failure type movement: ...
   - Trace movement: ...
   - Side effects to watch: ...
   ## Falsification
   ...
   ```

HARD CONSTRAINTS: Do NOT edit any source under `source_snapshot/`. Do NOT write
`pending_eval.json`. Do NOT append to `world_model_calibration.md`. Stop
immediately after writing `./prediction.md`.
