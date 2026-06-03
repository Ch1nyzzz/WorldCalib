#!/usr/bin/env bash
# WorldCalib launcher: ARC-AGI-2, calib variant — prose WMC + two-sided
# (per-grid-size-change) prediction, self-graded after eval (self-distill, no
# external critic, no gate). The solver is single-shot: each ARC task is solved
# by one chat call to the served target model, scored by exact grid match pass@2.
#
# Proposer (kimi via docker-claude-kimi) gets a ~1.5h-style per-iteration budget
# (PROPOSE_TIMEOUT_S=5400). 30 iters by default.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

for v in KIMI_API_KEY; do
  if [ -z "${!v:-}" ]; then
    printf 'fatal: %s is not set.\n' "$v" >&2
    exit 2
  fi
done

if [[ "$KIMI_API_KEY" == sk-kimi-* ]]; then
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.kimi.com/coding}"
else
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.moonshot.ai/anthropic}"
fi
KIMI_MODEL="${KIMI_MODEL:-kimi-k2.6}"

unset DIFF_EMBEDDING_MODEL
unset OPENAI_BASE_URL
export ENABLE_TOOL_SEARCH=false
export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-30}"
EVAL_WORKERS="${EVAL_WORKERS:-64}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-300}"
# ~1.5h per-iteration proposer budget.
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

# Served target model used by the single-shot ARC solver.
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
TARGET_API_KEY="${TARGET_API_KEY:-EMPTY}"

# ARC data / split sizing.
ARC_DATA_DIR="${ARC_DATA_DIR:-/data/home/yuhan/ARC-AGI-2/data}"
ARC_TRAIN_SIZE="${ARC_TRAIN_SIZE:-40}"
ARC_TEST_SIZE="${ARC_TEST_SIZE:-40}"
ARC_MAX_TOKENS="${ARC_MAX_TOKENS:-2048}"
ARC_MAX_ATTEMPTS="${ARC_MAX_ATTEMPTS:-2}"
ARC_RUNS="${ARC_RUNS:-1}"
ARC_CONCURRENCY="${ARC_CONCURRENCY:-8}"

DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs

run_id="arc_agi2_claudekimi_k26_maxeffort_target_${TARGET_MODEL//[^A-Za-z0-9]/_}_calib_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"
status_file="logs/launch_arc_calib_${TS}.status"
printf '[%s] START %s variant=calib iter=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "$ITERATIONS" "$(date -Is)" "$log_path" \
  | tee "$status_file"

setsid python -m worldcalib.optimize_cli \
  --arc-agi2 \
  --proposer-variant calib \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  --selection-policy default \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --iterations "$ITERATIONS" \
  --split train \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --model "$TARGET_MODEL" \
  --base-url "$TARGET_BASE_URL" \
  --api-key "$TARGET_API_KEY" \
  --arc-data-dir "$ARC_DATA_DIR" \
  --arc-train-size "$ARC_TRAIN_SIZE" \
  --arc-test-size "$ARC_TEST_SIZE" \
  --arc-max-tokens "$ARC_MAX_TOKENS" \
  --arc-max-attempts "$ARC_MAX_ATTEMPTS" \
  --arc-runs "$ARC_RUNS" \
  --arc-concurrency "$ARC_CONCURRENCY" \
  --proposer-agent claude \
  --claude-base-url "$KIMI_BASE_URL" \
  --claude-auth-token "$KIMI_API_KEY" \
  --claude-model "$KIMI_MODEL" \
  --claude-effort max \
  --proposer-sandbox docker \
  --proposer-docker-image docker-claude-kimi:latest \
  --proposer-docker-user "$DOCKER_USER_SPEC" \
  --proposer-docker-home /tmp \
  --proposer-docker-env KIMI_API_KEY \
  --proposer-docker-env ENABLE_TOOL_SEARCH \
  --proposer-docker-env CLAUDE_CODE_SUBAGENT_MODEL \
  --proposer-docker-env ANTHROPIC_DEFAULT_OPUS_MODEL \
  --proposer-docker-env ANTHROPIC_DEFAULT_SONNET_MODEL \
  --proposer-docker-env ANTHROPIC_DEFAULT_HAIKU_MODEL \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID %s %s\n' "$(date -Is)" "$run_id" "$pid" | tee -a "$status_file"
echo "$pid" > "logs/${run_id}.pid"
printf 'started pid=%s run_id=%s\nlog: %s\n' "$pid" "$run_id" "$log_path"
