#!/usr/bin/env bash
# WorldCalib launcher: LoCoMo, calib variant — prose WMC + two-sided prediction
# graded after eval by an external critic (same docker-kimi invocation as the
# proposer, fresh context). No in-loop critic, no gate. 30 iters by default.
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
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
BASELINE_LOCOMO_DIR="${BASELINE_LOCOMO_DIR:-runs/baseline_locomo_target_deepseek_v4_flash_20260526}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs
# No --baseline-dir: the precomputed locomo baseline was scored before the
# per-category score_breakdown change, so it only has an "all" bucket. Letting
# the optimizer evaluate the seed scaffold itself at iter 0 (with the current
# eval) gives a per-category iter-0 baseline that `clean`-based predictions can
# be graded against.

run_id="locomo_claudekimi_k26_maxeffort_target_deepseek_v4_flash_calib_bestofn3_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"
status_file="logs/launch_bestofn_locomo_${TS}.status"

# Aligned iter-0: clone a FIXED iter-0 seed (full per-episode evidence) and
# continue from iter 1 via --skip-scaffold-eval, instead of self-evaluating a
# fresh (variance-laden, unaligned) iter-0. Default seed = the same baseline the
# 0.47 reference run started from.
SEED_FROM="${SEED_FROM:-$BASELINE_LOCOMO_DIR}"
SEED_ARG=()
if [ -n "$SEED_FROM" ]; then
  if [ ! -d "$SEED_FROM/candidate_results" ]; then
    printf 'fatal: SEED_FROM=%q has no candidate_results/ (not an iter-0 seed)\n' "$SEED_FROM" >&2
    exit 2
  fi
  mkdir -p "runs/${run_id}"
  cp -a "$SEED_FROM"/. "runs/${run_id}/"
  rm -f "runs/${run_id}/optimizer_summary.json" "runs/${run_id}/run_summary.json"
  SEED_ARG=(--skip-scaffold-eval)
fi

printf '[%s] START %s variant=calib iter=%s seed_from=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "$ITERATIONS" "$SEED_FROM" "$(date -Is)" "$log_path" \
  | tee "$status_file"

setsid worldcalib-optimize \
  --locomo \
  --proposer-variant calib \
  --bestofn-k 3 \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  --selection-policy default \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  "${SEED_ARG[@]}" \
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
