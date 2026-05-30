#!/usr/bin/env bash
# WorldCalib launcher: LoCoMo, ledger + adversarial-critic proposer variant.
# Same config as the longmemeval critic run (--proposer-variant critic, soft
# gate, no --organized needed). 30 iters by default.
#   CRITIC_ENFORCE=1 hardens the gate; ITERATIONS overrides the count.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

for v in KIMI_API_KEY DEEPSEEK_API_KEY OPENAI_API_KEY; do
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
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
BASELINE_LOCOMO_DIR="${BASELINE_LOCOMO_DIR:-runs/baseline_locomo_target_deepseek_v4_flash_20260526}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

enforce_args=()
if [ "${CRITIC_ENFORCE:-0}" = "1" ]; then
  enforce_args=(--critic-gate-enforce)
fi

mkdir -p logs runs
if [ ! -f "${BASELINE_LOCOMO_DIR}/run_summary.json" ]; then
  printf 'fatal: baseline missing %s/run_summary.json\n' "$BASELINE_LOCOMO_DIR" >&2
  exit 1
fi

run_id="locomo_claudekimi_k26_maxeffort_target_deepseek_v4_flash_critic_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"
status_file="logs/launch_wmc_critic_locomo_${TS}.status"
printf '[%s] START %s variant=critic enforce=%s iter=%s baseline=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "${CRITIC_ENFORCE:-0}" "$ITERATIONS" "$BASELINE_LOCOMO_DIR" "$(date -Is)" "$log_path" \
  | tee "$status_file"

setsid worldcalib-optimize \
  --locomo \
  --proposer-variant critic \
  "${enforce_args[@]}" \
  --selection-policy default \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --baseline-dir "$BASELINE_LOCOMO_DIR" \
  --iterations "$ITERATIONS" \
  --split train \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --model "$TARGET_MODEL" \
  --base-url "$TARGET_BASE_URL" \
  --api-key EMPTY \
  --scaffolds memgpt_source \
  --scaffold-extra-json @/data/home/yuhan/Optimizer1/configs/source_memory.example.json \
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
