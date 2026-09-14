# Protocol and provenance

This release restores the 169-line calibration addon from development commit
`7635149c2b9dd3d62c0177689f58af60e5e9ae9f`, also present in the inspected
working checkout. Appendix B describes that protocol. Its release path is
`src/worldcalib/prompts/skills/shared/_calib_addon.md`.

The calibrated proposer receives `world_model_calibration.md` and its immediate
previous prediction as `prev_prediction.md`. Both arms receive the same runtime
configuration, source surface, raw evaluation evidence and score history.
The world model has Beliefs, Experiments and Calibration sections, plus an
append-only distillation history. The proposer predicts, observes and corrects
its own beliefs; the harness preserves the history.

The extended Task map, Residual coverage, prescribed tier taxonomy, machine
aggregate-bet grading, seed-task table and extra prediction-history injection
are removed. Diagnosing causal failures from traces and predicting a subset's
aggregate response remain part of the paper protocol.

Only five main benchmarks and two reported diagnostics are distributed. The
CLI exposes only LongMemEval-s. This cleanup does not change historical results.

## Reproduction boundary

The source implements the paper-specified protocol but does not contain all
original environments, trajectories or staged prompts. Use archived
`PROPOSER_SKILL.md` files to establish exact historical prompt provenance;
line counts alone cannot establish which version a past run consumed.

The included `belief_fidelity.py` is a simplified two-arm diagnostic, not the
full 40-candidate, three-arm, two-judge experiment. It omits the falsified-document
control and uses leave-one-block-out final world models; other parts of a final
document can still encode later outcomes. Its outputs are not an exact
reproduction of the paper's ablation table.

For comparable reruns, record the source commit, resolved Skill, external
repository commits, package versions, container image digests, frozen split,
baseline hash, provider endpoint/model identifiers and evaluation settings.
Keep credentials out of published manifests. Exact historical manifests are
not supplied by this release.
