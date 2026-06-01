#!/usr/bin/env bash
# Resume an existing critic-variant run to ITERATIONS total iters.
# Reuses the run dir, baseline, and all proposer wiring; --resume picks up at
# max(completed)+1. Same critic variant + soft gate as the pilot launcher.
#
# Usage:
#   RUN_ID=<existing_run_id> ITERATIONS=30 bash scripts/launch_wmc_critic_resume.sh
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

: "${RUN_ID:?set RUN_ID=<existing run id under runs/>}"
RUN_DIR="runs/${RUN_ID}"
if [ ! -f "${RUN_DIR}/runstore.db" ]; then
  printf 'fatal: %s/runstore.db not found — nothing to resume.\n' "$RUN_DIR" >&2
  exit 1
fi

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

ITERATIONS="${ITERATIONS:-30}"
CLAUDE_EFFORT="${CLAUDE_EFFORT:-max}"
EVAL_WORKERS="${EVAL_WORKERS:-64}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-300}"
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
LME_JUDGE_MODEL="${LME_JUDGE_MODEL:-deepseek-v4-flash}"
LME_JUDGE_BASE_URL="${LME_JUDGE_BASE_URL:-https://api.deepseek.com}"
BASELINE_LME_DIR="${BASELINE_LME_DIR:-runs/baseline_longmemeval_s_target_deepseek_v4_flash_fixedjudge_20260526}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

enforce_args=()
if [ "${CRITIC_ENFORCE:-1}" = "1" ]; then
  enforce_args=(--critic-gate-enforce)
fi

TS="$(date +%Y%m%d_%H%M%S)"
log_path="logs/${RUN_ID}_resume_to${ITERATIONS}_${TS}.log"
printf 'resuming %s -> %s iters (enforce=%s)\nlog: %s\n' \
  "$RUN_ID" "$ITERATIONS" "${CRITIC_ENFORCE:-0}" "$log_path"

setsid worldcalib-optimize \
  --longmemeval --longmemeval-variant s \
  --longmemeval-judge-model "$LME_JUDGE_MODEL" \
  --longmemeval-judge-base-url "$LME_JUDGE_BASE_URL" \
  --proposer-variant critic \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  "${enforce_args[@]}" \
  --resume \
  --selection-policy default \
  --no-summary \
  --run-id "$RUN_ID" \
  --out "$RUN_DIR" \
  --baseline-dir "$BASELINE_LME_DIR" \
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
  --claude-effort "$CLAUDE_EFFORT" \
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
printf 'resumed pid=%s\n' "$pid"
echo "$pid" > "logs/${RUN_ID}_resume.pid"
