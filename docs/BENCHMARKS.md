# Benchmark scope

The release follows the paper rather than the historical development tree.

| Role | Benchmark | Train | Held-out | Grading / split note |
|---|---|---:|---:|---|
| Main | LongMemEval-s | 100 | 400 | Deterministic split; LLM judge by default |
| Main | LoCoMo | 80 | 1,449 | Answerable categories; deterministic split |
| Main | GAIA L1+L2 | 40 | 99 | Exact match; pinned Hugging Face revision |
| Main | AppWorld | 45 | 372 | Scenario-disjoint challenge + challenge-ext split |
| Main | Terminal-Bench 2.0 | 20 | 67 | Execution graded; 66 held-out tasks are evaluable under the paper's 20 GB sandbox cap |
| Diagnostic | Spider2-lite | 31 | 104 | Database-disjoint; execution-based SQL grading |
| Diagnostic | Toolathlon | 36 | 64 | App-disjoint local diagnostic split; 8 credential/infrastructure tasks are excluded |

The main result set contains the first five rows. Spider2-lite and Toolathlon
are retained because the paper uses them to characterize the operating regime
and failure modes. WebShop and OS experiments are deliberately not shipped.

## Split resources

- AppWorld: `split_challenge.json` and `split_challenge_ext.json` are combined
  and validated as 45/372 with no overlap.
- Terminal-Bench 2.0: `split.json` is validated as 20/67. The loader applies
  the paper's symmetric storage cap at evaluation time.
- Spider2-lite: `split.json` is validated as 31/104 with no overlap.
- Toolathlon: `split.json` is validated as 36/64/8 across train, test, and
  excluded sets.
- GAIA: L1+L2 tasks are loaded from revision
  `682dd723ee1e1697e00360edccf2366dc8418dd9`; the first 40 form train and the
  remaining 99 form held-out.
- LongMemEval-s and LoCoMo splits are deterministically materialized next to
  the operator-provided data file. Keep the generated split fixed across arms.

## External resources

Benchmark contents are not redistributed. Configure them explicitly:

| Variable / CLI flag | Expected resource |
|---|---|
| `--data-path`, `--split-path` | LoCoMo or LongMemEval JSON and frozen split |
| `HF_TOKEN` | Access to the gated GAIA dataset, when required |
| `APPWORLD_ROOT`, `APPWORLD_PYTHON` | AppWorld data root and isolated interpreter |
| `SPIDER2_ROOT` | `spider2-lite` directory containing JSONL, databases, and evaluator |
| `TOOLATHLON_ROOT` | Toolathlon checkout |
| `TB2_TASKS_PATH` | Terminal-Bench 2.0 Harbor task directory |
| `TB2_TERMINUS2_SOURCE` | Parent of the editable `terminus_2` package |

Relative CLI paths resolve against `--work-dir`, never against an installed
module's location.
