#!/usr/bin/env bash
# WorldCalib launcher: Spider2-lite (local sqlite subset), WMC-vs-noWMC.
# One parameterized script for both arms; the first positional arg (or $VARIANT):
#   calib  -> self-distill WMC (no external critic). Routes to spider2_calib skill.
#   nowmc  -> the no-WMC ablation (pure-default contract). Routes to spider2_nowmc.
#
# Spider2 runs from the MAIN venv: the agent is a single-shot text-to-SQL policy
# whose only deps are openai/pandas (pandas via the vendored evaluation_suite,
# plus google-cloud-bigquery which the suite imports at module top even for the
# local sqlite path). The target SUT is DeepSeek-V4-Flash on the shared GPUGeek
# solver account (Solver_API_KEY), wired via MODEL_NAME / DEEPSEEK_BASE_URL /
# DEEPSEEK_API_KEY — there is no --model/--base-url/--api-key (those are unused
# by the Spider2 backend). The
# proposer is kimi via docker-claude-kimi, identical to the other launchers.
#
# Shared iter-0 seed: SEED_FROM clones a precomputed iter-0 run dir into this
# arm and continues from iter 1 via --skip-scaffold-eval, so both arms start
# byte-identical at iter 0 and diverge only by the calibration treatment.
#
# Usage (from repo root):
#   ITERATIONS=0 scripts/launch_spider2.sh nowmc           # build the shared seed
#   SEED_FROM=runs/<seed_run> scripts/launch_spider2.sh calib
#   SEED_FROM=runs/<seed_run> scripts/launch_spider2.sh nowmc
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VARIANT="${1:-${VARIANT:-calib}}"
case "$VARIANT" in
  calib|nowmc) ;;
  *) printf 'fatal: VARIANT must be calib or nowmc (got %q)\n' "$VARIANT" >&2; exit 2 ;;
esac

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

for v in KIMI_API_KEY Solver_API_KEY; do
  if [ -z "${!v:-}" ]; then
    printf 'fatal: %s is not set.\n' "$v" >&2
    exit 2
  fi
done

# Main venv python (must have worldcalib + openai + pandas + google-cloud-bigquery).
SPIDER2_PY="${SPIDER2_PY:-python}"

# The frozen SUT runs on the shared GPUGeek solver account (Solver_API_KEY) —
# the same endpoint/model the putty configs pin as their frozen solver. It stays
# DeepSeek-V4-**Flash**: the .env SOLVER_MODEL names V4-Pro, and swapping the SUT
# would confound the one thing the re-run measures (whether the proposer's new
# evidence moves the stable failures) with "a stronger model solves more".
#
# spider2/llm.py drives the OpenAI SDK directly off DEEPSEEK_BASE_URL /
# DEEPSEEK_API_KEY / MODEL_NAME, so point those at the solver. Note the model id
# takes NO "openai/" prefix here (that is a LiteLLM-ism and would 404).
export DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-${SOLVER_BASE_URL:-https://api.gpugeek.com/v1}}"
export DEEPSEEK_API_KEY="${Solver_API_KEY}"
export MODEL_NAME="${MODEL_NAME:-Vendor3/DeepSeek-V4-Flash}"

if [[ "$KIMI_API_KEY" == sk-kimi-* ]]; then
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.kimi.com/coding}"
else
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.moonshot.ai/anthropic}"
fi
KIMI_MODEL="${KIMI_MODEL:-kimi-k2.7}"

unset DIFF_EMBEDDING_MODEL
unset OPENAI_BASE_URL
export ENABLE_TOOL_SEARCH=false
export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-20}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

# Spider2 eval config. Frozen split data/spider2/lite_local_split.json owns the
# train/test instance ids (31 train / 104 test, db-disjoint).
SPIDER2_CONCURRENCY="${SPIDER2_CONCURRENCY:-8}"
SPIDER2_RUNS="${SPIDER2_RUNS:-1}"

SELECTION_POLICY="${SELECTION_POLICY:-self}"
SEED_FROM="${SEED_FROM:-}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs

run_id="spider2_local_claudekimi_k27_maxeffort_${VARIANT}_iter${ITERATIONS}_${TS}"

resume_args=()
if [ -n "${RESUME_RUN_ID:-}" ]; then
  run_id="$RESUME_RUN_ID"
  if [ ! -d "runs/${run_id}/candidate_results" ]; then
    printf 'fatal: RESUME_RUN_ID=%q has no runs/%s/candidate_results to resume from.\n' \
      "$run_id" "$run_id" >&2
    exit 2
  fi
  resume_args=(--resume)
  SEED_FROM=""
fi

log_path="logs/${run_id}.log"
status_file="logs/launch_spider2_${VARIANT}_${TS}.status"

SEED_ARG=()
if [ -n "$SEED_FROM" ]; then
  if [ ! -d "$SEED_FROM/candidate_results" ]; then
    printf 'fatal: SEED_FROM=%q has no candidate_results/ (not an iter-0 run dir)\n' "$SEED_FROM" >&2
    exit 2
  fi
  mkdir -p "runs/${run_id}"
  cp -a "$SEED_FROM"/. "runs/${run_id}/"
  rm -f "runs/${run_id}/optimizer_summary.json" "runs/${run_id}/run_summary.json"
  SEED_ARG=(--skip-scaffold-eval)
fi

printf '[%s] START %s variant=%s iter=%s seed_from=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "$VARIANT" "$ITERATIONS" "${SEED_FROM:-<self-eval>}" \
  "$(date -Is)" "$log_path" \
  | tee "$status_file"

setsid "$SPIDER2_PY" -m worldcalib.optimize_cli \
  --spider2 \
  --spider2-concurrency "$SPIDER2_CONCURRENCY" \
  --spider2-runs "$SPIDER2_RUNS" \
  --proposer-variant "$VARIANT" \
  "${resume_args[@]}" \
  "${SEED_ARG[@]}" \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  --selection-policy "$SELECTION_POLICY" \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --iterations "$ITERATIONS" \
  --split train \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --proposer-agent claude \
  --claude-base-url "$KIMI_BASE_URL" \
  --claude-auth-token "$KIMI_API_KEY" \
  --claude-model "$KIMI_MODEL" \
  --claude-effort max \
  --proposer-sandbox docker \
  --proposer-docker-image docker-claude-kimi:latest \
  --proposer-docker-user "$DOCKER_USER_SPEC" \
  --proposer-docker-home /tmp \
  --proposer-docker-mount "$PWD/third_party/Spider2/spider2-lite/resource/databases:/spider2_db:ro" \
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
printf 'started pid=%s run_id=%s variant=%s\nlog: %s\n' "$pid" "$run_id" "$VARIANT" "$log_path"
