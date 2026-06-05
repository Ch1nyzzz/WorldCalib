#!/usr/bin/env bash
# WorldCalib launcher: AgentBench best-of-N selection variants.
#
# Same recipe as launch_webshop.sh (kimi docker proposer, deepseek-v4-flash
# target, frozen split), but adds the candidate-selection mode:
#   SELECT_MODE=fanout  -> --fanout-k $SELECT_K  (K parallel proposer agents +
#                          independent orchestrator selector)
#   SELECT_MODE=bestofn -> --bestofn-k $SELECT_K (ONE proposer fully implements
#                          K candidates + independent selector)
#   SELECT_MODE=none    -> classic single proposer (no extra flag)
# Selection is gated by --proposer-variant calib (the world-model variant).
#
# Usage:
#   SELECT_MODE=fanout  SELECT_K=3 AGENTBENCH_TASK=os ITERATIONS=1 scripts/launch_agentic_select.sh
#   SELECT_MODE=bestofn SELECT_K=3 AGENTBENCH_TASK=os ITERATIONS=1 scripts/launch_agentic_select.sh
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

SELECT_MODE="${SELECT_MODE:-fanout}"
SELECT_K="${SELECT_K:-3}"
case "$SELECT_MODE" in
  fanout)  SELECT_ARG=(--fanout-k "$SELECT_K") ;;
  bestofn) SELECT_ARG=(--bestofn-k "$SELECT_K") ;;
  none)    SELECT_ARG=() ;;
  *) printf 'fatal: SELECT_MODE must be fanout|bestofn|none (got %q)\n' "$SELECT_MODE" >&2; exit 2 ;;
esac

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
for v in KIMI_API_KEY DEEPSEEK_API_KEY; do
  if [ -z "${!v:-}" ]; then printf 'fatal: %s is not set.\n' "$v" >&2; exit 2; fi
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
ITERATIONS="${ITERATIONS:-20}"
EVAL_WORKERS="${EVAL_WORKERS:-24}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-300}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

AGENTBENCH_TASK="${AGENTBENCH_TASK:-os}"
CONTROLLER_URL="${CONTROLLER_URL:-http://localhost:5020/api}"
AGENTBENCH_TRAIN_SIZE="${AGENTBENCH_TRAIN_SIZE:-30}"
AGENTBENCH_TEST_SIZE="${AGENTBENCH_TEST_SIZE:-40}"
AGENTBENCH_CONCURRENCY="${AGENTBENCH_CONCURRENCY:-24}"
AGENTBENCH_RUNS="${AGENTBENCH_RUNS:-1}"

TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
TARGET_API_KEY="${TARGET_API_KEY:-$DEEPSEEK_API_KEY}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs
run_id="${AGENTBENCH_TASK}_select_${SELECT_MODE}${SELECT_K}_target_${TARGET_MODEL//[^A-Za-z0-9]/_}_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"

printf '[%s] START %s mode=%s k=%s iter=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "$SELECT_MODE" "$SELECT_K" "$ITERATIONS" "$(date -Is)" "$log_path"

setsid python -m worldcalib.optimize_cli \
  --agentbench \
  --agentbench-task "$AGENTBENCH_TASK" \
  --controller-url "$CONTROLLER_URL" \
  --proposer-variant calib \
  "${SELECT_ARG[@]}" \
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
  --agentbench-train-size "$AGENTBENCH_TRAIN_SIZE" \
  --agentbench-test-size "$AGENTBENCH_TEST_SIZE" \
  --agentbench-concurrency "$AGENTBENCH_CONCURRENCY" \
  --agentbench-runs "$AGENTBENCH_RUNS" \
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
echo "$pid" > "logs/${run_id}.pid"
printf 'started pid=%s run_id=%s mode=%s k=%s\nlog: %s\n' "$pid" "$run_id" "$SELECT_MODE" "$SELECT_K" "$log_path"
