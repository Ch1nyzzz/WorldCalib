#!/usr/bin/env bash
# WorldCalib launcher: default arm + --no-summary + WMC, mirrored from
# Optimizer1's scripts/launch_claudekimi_target_deepseek_v4_flash_nosummary_nostate.sh
# but stripped to one arm (default) and routed through `worldcalib-optimize`
# so the calibration mechanism kicks in automatically.
#
# Proposer:   claude CLI inside docker-claude-kimi:latest, routed to
#             api.kimi.com/coding at kimi-k2.6 --effort max.
# Target:     deepseek-v4-flash on api.deepseek.com (key from $DEEPSEEK_API_KEY).
# Baselines:  reuses the two iter-0 runs already in runs/ (copied from
#             Optimizer1) so we don't repay the baseline eval.
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
    printf 'fatal: %s is not set; populate .env or export it.\n' "$v" >&2
    exit 2
  fi
done

if [[ "$KIMI_API_KEY" == sk-kimi-* ]]; then
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.kimi.com/coding}"
else
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.moonshot.ai/anthropic}"
fi
KIMI_MODEL="${KIMI_MODEL:-kimi-k2.6}"

# Embeddings: OpenAI official text-embedding-3-small. Unset overrides so the
# SDK uses defaults; claude_runner.DEFAULT_DOCKER_ENV_VARS forwards
# OPENAI_API_KEY / OPENAI_BASE_URL / DIFF_EMBEDDING_MODEL into the proposer
# container.
unset DIFF_EMBEDDING_MODEL
unset OPENAI_BASE_URL

# claude 2.1.85 inside docker-claude-kimi: disable tool-search; pin every
# model alias to kimi-k2.6 so the endpoint never sees a sonnet/opus/haiku
# alias it can't serve.
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
LME_JUDGE_MODEL="${LME_JUDGE_MODEL:-deepseek-v4-flash}"
LME_JUDGE_BASE_URL="${LME_JUDGE_BASE_URL:-https://api.deepseek.com}"
BASELINE_LOCOMO_DIR="${BASELINE_LOCOMO_DIR:-runs/baseline_locomo_target_deepseek_v4_flash_20260526}"
BASELINE_LME_DIR="${BASELINE_LME_DIR:-runs/baseline_longmemeval_s_target_deepseek_v4_flash_fixedjudge_20260526}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs
status_file="logs/launch_wmc_default_nosummary_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s proposer=claudekimi(%s) target=%s judge=%s no_summary=1 wmc=1\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "$KIMI_MODEL" "$TARGET_MODEL" "$LME_JUDGE_MODEL" >> "$status_file"
printf '[%s] BASELINE_LOCOMO_DIR=%s\n' "$(date -Is)" "$BASELINE_LOCOMO_DIR" >> "$status_file"
printf '[%s] BASELINE_LME_DIR=%s\n' "$(date -Is)" "$BASELINE_LME_DIR" >> "$status_file"

for d in "$BASELINE_LOCOMO_DIR" "$BASELINE_LME_DIR"; do
  if [ ! -f "${d}/run_summary.json" ]; then
    printf 'fatal: baseline missing %s/run_summary.json\n' "$d" >&2
    exit 1
  fi
done

proposer_args=(
  --proposer-agent claude
  --claude-base-url "$KIMI_BASE_URL"
  --claude-auth-token "$KIMI_API_KEY"
  --claude-model "$KIMI_MODEL"
  --claude-effort max
  --proposer-sandbox docker
  --proposer-docker-image docker-claude-kimi:latest
  --proposer-docker-user "$DOCKER_USER_SPEC"
  --proposer-docker-home /tmp
  --proposer-docker-env KIMI_API_KEY
  --proposer-docker-env ENABLE_TOOL_SEARCH
  --proposer-docker-env CLAUDE_CODE_SUBAGENT_MODEL
  --proposer-docker-env ANTHROPIC_DEFAULT_OPUS_MODEL
  --proposer-docker-env ANTHROPIC_DEFAULT_SONNET_MODEL
  --proposer-docker-env ANTHROPIC_DEFAULT_HAIKU_MODEL
)

start_one() {
  local task="$1"
  local task_label task_args=() baseline_dir run_id log_path

  if [ "$task" = "locomo" ]; then
    task_label="locomo"
    task_args=(--locomo)
    baseline_dir="$BASELINE_LOCOMO_DIR"
  else
    task_label="longmemeval_s"
    task_args=(
      --longmemeval --longmemeval-variant s
      --longmemeval-judge-model "$LME_JUDGE_MODEL"
      --longmemeval-judge-base-url "$LME_JUDGE_BASE_URL"
    )
    baseline_dir="$BASELINE_LME_DIR"
  fi

  run_id="${task_label}_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter${ITERATIONS}_${TS}"
  log_path="logs/${run_id}.log"

  printf '[%s] START %s baseline=%s\n[%s] LOG   %s\n' \
    "$(date -Is)" "$run_id" "$baseline_dir" "$(date -Is)" "$log_path" >> "$status_file"

  setsid worldcalib-optimize \
    "${task_args[@]}" \
    --selection-policy default \
    --no-summary \
    --run-id "$run_id" \
    --out "runs/${run_id}" \
    --baseline-dir "$baseline_dir" \
    --iterations "$ITERATIONS" \
    --split train \
    --eval-workers "$EVAL_WORKERS" \
    --eval-timeout-s "$EVAL_TIMEOUT_S" \
    --model "$TARGET_MODEL" \
    --base-url "$TARGET_BASE_URL" \
    --api-key EMPTY \
    --scaffolds memgpt_source \
    --scaffold-extra-json @/data/home/yuhan/Optimizer1/configs/source_memory.example.json \
    "${proposer_args[@]}" \
    > "$log_path" 2>&1 < /dev/null &

  local pid=$!
  printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
  printf '%s %s %s\n' "$pid" "$run_id" "$log_path"
}

start_one locomo
start_one longmemeval

printf '[%s] LAUNCHER dispatched — see %s\n' "$(date -Is)" "$status_file" >> "$status_file"
printf '\nstatus: %s\n' "$status_file"
