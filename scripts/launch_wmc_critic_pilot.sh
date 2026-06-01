#!/usr/bin/env bash
# WorldCalib launcher: ledger + adversarial-critic proposer variant.
# Same proposer/target/baseline wiring as launch_wmc_default_nosummary.sh, but:
#   - --proposer-variant critic   (routes to the longmemeval_critic skill;
#     no prose world_model_calibration.md, ledger + critic-subagent protocol)
#   - longmemeval only, short ITERATIONS by default (pilot).
#   - critic gate left SOFT (compliance logged, not enforced) until a pilot
#     confirms the critic flow runs end-to-end; set CRITIC_ENFORCE=1 to harden.
#
# The RunStore MCP tools (trace_similar etc.) are registered in every mode, so
# the critic variant needs NO --organized flag.
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

# Embeddings: OpenAI official text-embedding-3-small (trace_similar backend).
unset DIFF_EMBEDDING_MODEL
unset OPENAI_BASE_URL

export ENABLE_TOOL_SEARCH=false
export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
# The critic subagent runs as a Claude Code subagent inside the proposer
# session; pin it to kimi too.
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-5}"
EVAL_WORKERS="${EVAL_WORKERS:-64}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-300}"
# Proposer hard budget: 1.5h. kimi max-effort needs the room; on overrun the
# runner now docker-kills the orphaned container (no more leaked sessions).
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
LME_JUDGE_MODEL="${LME_JUDGE_MODEL:-deepseek-v4-flash}"
LME_JUDGE_BASE_URL="${LME_JUDGE_BASE_URL:-https://api.deepseek.com}"
BASELINE_LME_DIR="${BASELINE_LME_DIR:-runs/baseline_longmemeval_s_target_deepseek_v4_flash_fixedjudge_20260526}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

# Hard gate by default (critic veto + no-optimism-discount); CRITIC_ENFORCE=0 softens it.
enforce_args=()
if [ "${CRITIC_ENFORCE:-1}" = "1" ]; then
  enforce_args=(--critic-gate-enforce)
fi

mkdir -p logs runs
status_file="logs/launch_wmc_critic_pilot_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s variant=critic enforce=%s proposer=claudekimi(%s) target=%s\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "${CRITIC_ENFORCE:-0}" "$KIMI_MODEL" "$TARGET_MODEL" >> "$status_file"

if [ ! -f "${BASELINE_LME_DIR}/run_summary.json" ]; then
  printf 'fatal: baseline missing %s/run_summary.json\n' "$BASELINE_LME_DIR" >&2
  exit 1
fi

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

run_id="longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_critic_pilot_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"

printf '[%s] START %s baseline=%s\n[%s] LOG   %s\n' \
  "$(date -Is)" "$run_id" "$BASELINE_LME_DIR" "$(date -Is)" "$log_path" >> "$status_file"

setsid worldcalib-optimize \
  --longmemeval --longmemeval-variant s \
  --longmemeval-judge-model "$LME_JUDGE_MODEL" \
  --longmemeval-judge-base-url "$LME_JUDGE_BASE_URL" \
  --proposer-variant critic \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  "${enforce_args[@]}" \
  --selection-policy default \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --baseline-dir "$BASELINE_LME_DIR" \
  --iterations "$ITERATIONS" \
  --split train \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --model "$TARGET_MODEL" \
  --base-url "$TARGET_BASE_URL" \
  --api-key EMPTY \
  --scaffolds memgpt_source \
  --scaffold-extra-json @/data/home/yuhan/Optimizer1/configs/source_memory.example.json \
  "${proposer_args[@]}" \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
printf 'started pid=%s run_id=%s\nlog: %s\nstatus: %s\n' "$pid" "$run_id" "$log_path" "$status_file"
