#!/usr/bin/env bash
# Evaluate a previously-optimized mini-SWE-agent candidate on the FULL
# SWE-bench Verified 500-task test set. This is pure EVALUATION (one pass over
# 500 tasks: agent run + official swebench harness), NOT optimization.
#
# Parametrized by VARIANT (calib | nowmc). The two arms are the matched
# 20260605_212552 ablation pair: calib = WMC self-distill, nowmc = pure default.
#   calib -> iter_005 submission_hardening
#   nowmc -> iter_004 auto_search_from_task
#
#   solver : deepseek-v4-flash (mini-SWE-agent), via the eval-gate script
#   data   : data/swebench_verified_all500_test.json  (all 500, split=test)
#   eval   : official swebench.harness.run_evaluation on SWE-Bench_Verified
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VARIANT="${VARIANT:?set VARIANT=calib|nowmc}"
case "$VARIANT" in
  calib)
    SRC="runs/swebench_fail15_claudekimi_k26_dsflash_calib_iter5_20260605_212552/proposer_calls/iter_005/source_snapshot/candidate/upstream_source/mini-swe-agent"
    CAND_ID="calib_iter005_submission_hardening"
    ;;
  nowmc)
    SRC="runs/swebench_fail15_claudekimi_k26_dsflash_nowmc_iter5_20260605_212552/proposer_calls/iter_004/source_snapshot/candidate/upstream_source/mini-swe-agent"
    CAND_ID="nowmc_iter004_auto_search_from_task"
    ;;
  *) printf 'fatal: VARIANT must be calib or nowmc, got %q\n' "$VARIANT" >&2; exit 2 ;;
esac

if [ ! -d "$SRC" ]; then
  printf 'fatal: candidate source missing: %s\n' "$SRC" >&2; exit 1
fi

if [ -f .env ]; then
  set -a; # shellcheck disable=SC1091
  source .env; set +a
fi
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  printf 'fatal: DEEPSEEK_API_KEY not set (populate .env)\n' >&2; exit 2
fi
# The evaluate script's run command does not pass --api-key-env; mini-SWE-agent's
# OpenAI-compatible client reads OPENAI_API_KEY from the environment.
export OPENAI_API_KEY="$DEEPSEEK_API_KEY"

# Use the venv that has worldcalib + uvx installed.
VENV_BIN="/data/home/yuhan/cyh_dev/bin"
export PATH="${VENV_BIN}:${PATH}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
DATA_PATH="${DATA_PATH:-data/swebench_verified_all500_test.json}"
EVAL_WORKERS="${EVAL_WORKERS:-8}"
TIMEOUT_S="${TIMEOUT_S:-900}"
# step-limit 0 => honor the candidate scaffold's own swebench_backticks.yaml
# (capped at 250 by run_miniswe_swebench_single.py). Do NOT use the eval
# script's default of 50, which would override the optimized scaffold.
STEP_LIMIT="${STEP_LIMIT:-0}"
MAX_TOKENS="${MAX_TOKENS:-4096}"
MODEL="${MODEL:-openai/deepseek-v4-flash}"
BASE_URL="${BASE_URL:-https://api.deepseek.com/v1}"

run_id="eval500_${VARIANT}_dsflash_${TS}"
out_dir="runs/${run_id}"
mkdir -p logs runs "$out_dir"
log_path="logs/${run_id}.log"

printf 'started VARIANT=%s candidate=%s\n  source=%s\n  out=%s\n  log=%s\n' \
  "$VARIANT" "$CAND_ID" "$SRC" "$out_dir" "$log_path"

setsid "${VENV_BIN}/python" scripts/evaluate_swebench_source_candidate.py \
  --data-path "$DATA_PATH" \
  --split test --limit 0 \
  --out "$out_dir" \
  --candidate-id "$CAND_ID" \
  --source-path "$SRC" \
  --model "$MODEL" \
  --base-url "$BASE_URL" \
  --eval-workers "$EVAL_WORKERS" \
  --timeout-s "$TIMEOUT_S" \
  --step-limit "$STEP_LIMIT" \
  --max-tokens "$MAX_TOKENS" \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf 'pid=%s run_id=%s\n' "$pid" "$run_id"
