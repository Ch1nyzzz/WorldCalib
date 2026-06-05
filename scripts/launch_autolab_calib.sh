#!/usr/bin/env bash
# WorldCalib launcher: AutoLab terminus-2 harness-config optimization (calib arm).
#
#   proposer : kimi-k2.6 via claude-code in docker-claude-kimi:latest
#   solver   : terminus-2 (in the cyh_dev harbor venv) driving --autolab-harbor-model
#   tasks    : AutoLab 36-task suite under third_party/autolab/tasks
#              (subset via AUTOLAB_TASK_IDS; empty = all 36)
#   variant  : calib -> autolab_calib skill (single-proposer self-distill WMC)
#
# The runner shells out to the cyh_dev harbor binary; that venv MUST be patched
# for GPU passthrough + 1200s command durations (see autolab.py / harbor_patch.sh),
# otherwise the 12 gpus=1 tasks fail. Set AUTOLAB_SKIP_PATCH_CHECK=1 to bypass the
# startup check when running CPU-only tasks on an intentionally-unpatched venv.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROPOSER_VARIANT="${PROPOSER_VARIANT:-calib}"
case "$PROPOSER_VARIANT" in
  calib|nowmc) ;;
  *) printf 'fatal: PROPOSER_VARIANT must be calib or nowmc, got %q\n' "$PROPOSER_VARIANT" >&2; exit 2 ;;
esac

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Proposer (kimi) key is mandatory; the solver model key (whichever provider
# --autolab-harbor-model uses) must be present in the harbor --env-file.
for v in KIMI_API_KEY; do
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

unset DIFF_EMBEDDING_MODEL
unset OPENAI_BASE_URL

export ENABLE_TOOL_SEARCH=false
export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-5}"
# AutoLab tasks each launch a long harbor docker trial; keep eval concurrency
# low and the per-harbor-run subprocess timeout generous (the runner also
# derives a per-task ceiling from task.toml).
EVAL_WORKERS="${EVAL_WORKERS:-2}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-9000}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

TASKS_PATH="${AUTOLAB_TASKS_PATH:-third_party/autolab/tasks}"
HARBOR_BINARY="${AUTOLAB_HARBOR_BINARY:-/data/home/yuhan/cyh_dev/bin/harbor}"
HARBOR_PYTHON="${AUTOLAB_HARBOR_PYTHON:-/data/home/yuhan/cyh_dev/bin/python}"
HARBOR_MODEL="${AUTOLAB_HARBOR_MODEL:-deepseek-v4-pro[1m]}"
HARBOR_ENV_FILE="${AUTOLAB_HARBOR_ENV_FILE:-.env}"
N_ATTEMPTS="${AUTOLAB_N_ATTEMPTS:-1}"
TIMEOUT_MULT="${AUTOLAB_TIMEOUT_MULTIPLIER:-1.0}"
HARBOR_CONC="${AUTOLAB_CONCURRENCY:-1}"
REWARD_GATE="${AUTOLAB_REWARD_GATE:-0.5}"
SCORE_MODE="${AUTOLAB_SCORE_MODE:-best}"
TASK_IDS="${AUTOLAB_TASK_IDS:-}"

if [ ! -d "$TASKS_PATH" ]; then
  printf 'fatal: AutoLab tasks dir missing %s\n' "$TASKS_PATH" >&2
  exit 1
fi
if [ ! -x "$HARBOR_BINARY" ]; then
  printf 'fatal: harbor binary not found/executable at %s\n' "$HARBOR_BINARY" >&2
  exit 1
fi

autolab_args=(
  --autolab
  --autolab-tasks-path "$TASKS_PATH"
  --autolab-harbor-binary "$HARBOR_BINARY"
  --autolab-harbor-python "$HARBOR_PYTHON"
  --autolab-harbor-model "$HARBOR_MODEL"
  --autolab-n-attempts "$N_ATTEMPTS"
  --autolab-timeout-multiplier "$TIMEOUT_MULT"
  --autolab-concurrency "$HARBOR_CONC"
  --autolab-reward-gate "$REWARD_GATE"
  --autolab-score-mode "$SCORE_MODE"
)
if [ -n "$HARBOR_ENV_FILE" ]; then
  autolab_args+=(--autolab-env-file "$HARBOR_ENV_FILE")
fi
if [ -n "$TASK_IDS" ]; then
  autolab_args+=(--autolab-task-ids "$TASK_IDS")
fi
if [ "${AUTOLAB_SKIP_PATCH_CHECK:-0}" = "1" ]; then
  autolab_args+=(--autolab-skip-patch-check)
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

mkdir -p logs runs
run_id="autolab_claudekimi_k26_${PROPOSER_VARIANT}_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"
status_file="logs/launch_autolab_${PROPOSER_VARIANT}_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s variant=%s proposer=claudekimi(%s) solver=%s tasks=%s\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "$PROPOSER_VARIANT" "$KIMI_MODEL" "$HARBOR_MODEL" "$TASKS_PATH" >> "$status_file"
printf '[%s] START %s\n[%s] LOG   %s\n' \
  "$(date -Is)" "$run_id" "$(date -Is)" "$log_path" >> "$status_file"

setsid worldcalib-optimize \
  "${autolab_args[@]}" \
  --split train \
  --proposer-variant "$PROPOSER_VARIANT" \
  --selection-policy pareto \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --iterations "$ITERATIONS" \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --api-key EMPTY \
  "${proposer_args[@]}" \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
printf 'started pid=%s run_id=%s variant=%s\nlog: %s\nstatus: %s\n' \
  "$pid" "$run_id" "$PROPOSER_VARIANT" "$log_path" "$status_file"
