#!/usr/bin/env bash
# Post-hoc calibration test launcher: no-WM vs calib-WM blind-judge comparison
# on a finished `calib` run's own candidates (leave-one-out world model).
#
#   ./scripts/launch_posthoc_calib.sh            # both LME + LoCoMo, full 30
#   LIMIT=3 ./scripts/launch_posthoc_calib.sh     # 3-candidate pilot each
#   CONCURRENCY=3 ./scripts/launch_posthoc_calib.sh
#
# Spawns only this experiment's own docker-kimi containers (named wc-proposer-*
# / wc-critic-* via the runner); does not touch any other run's containers.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -z "${KIMI_API_KEY:-}" ]; then
  echo "fatal: KIMI_API_KEY not set" >&2
  exit 2
fi

LME_RUN="${LME_RUN:-runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_calib_iter30_20260602_171707}"
LOCOMO_RUN="${LOCOMO_RUN:-runs/locomo_claudekimi_k26_maxeffort_target_deepseek_v4_flash_calib_iter30_20260602_190328}"
LIMIT="${LIMIT:-0}"
SAMPLE="${SAMPLE:-0}"
CONCURRENCY="${CONCURRENCY:-2}"
TIMEOUT_S="${TIMEOUT_S:-2400}"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p logs

run_one() {
  local tag="$1" run_dir="$2"
  local log="logs/posthoc_calib_${tag}_${TS}.log"
  echo "[posthoc] $tag run=$run_dir log=$log"
  python3 scripts/posthoc_calib_predict.py \
    --run-dir "$run_dir" \
    --limit "$LIMIT" \
    --sample "$SAMPLE" \
    --concurrency "$CONCURRENCY" \
    --timeout-s "$TIMEOUT_S" \
    > "$log" 2>&1
  echo "[posthoc] $tag DONE -> $(dirname "$log")"
}

run_one lme "$LME_RUN"
run_one locomo "$LOCOMO_RUN"
echo "[posthoc] all done"
