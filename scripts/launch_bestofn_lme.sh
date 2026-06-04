#!/usr/bin/env bash
# WorldCalib launcher: calib variant — prose WMC + two-sided prediction graded
# after eval by an external critic (prediction accuracy becomes an optimized
# scalar). No in-loop adversarial critic, no gate; candidates are selected by
# real eval + frontier, exactly like the prose/default run.
#
#   - --proposer-variant calib  (routes to the longmemeval_calib skill)
#   - longmemeval only by default; ITERATIONS overridable.
#
# The critic GRADER reuses the LongMemEval judge endpoint (deepseek) by default
# — no extra flags needed; it scores prediction.md vs the measured per-type
# outcome and writes critic_feedback.md for the next iter.
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
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-30}"
EVAL_WORKERS="${EVAL_WORKERS:-64}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-300}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
LME_JUDGE_MODEL="${LME_JUDGE_MODEL:-deepseek-v4-flash}"
LME_JUDGE_BASE_URL="${LME_JUDGE_BASE_URL:-https://api.deepseek.com}"
BASELINE_LME_DIR="${BASELINE_LME_DIR:-runs/baseline_longmemeval_s_target_deepseek_v4_flash_fixedjudge_20260526}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs
status_file="logs/launch_bestofn_lme_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s variant=calib proposer=claudekimi(%s) target=%s\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "$KIMI_MODEL" "$TARGET_MODEL" >> "$status_file"

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

run_id="longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_calib_bestofn3_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"

printf '[%s] START %s baseline=%s\n[%s] LOG   %s\n' \
  "$(date -Is)" "$run_id" "$BASELINE_LME_DIR" "$(date -Is)" "$log_path" >> "$status_file"

setsid worldcalib-optimize \
  --longmemeval --longmemeval-variant s \
  --longmemeval-judge-model "$LME_JUDGE_MODEL" \
  --longmemeval-judge-base-url "$LME_JUDGE_BASE_URL" \
  --proposer-variant calib \
  --bestofn-k 3 \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
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
