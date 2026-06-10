#!/usr/bin/env bash
# SWE-bench mini optimizer, solver model swapped to the SAME Gemini-3-flash that
# Terminal-Bench (terminus) uses: openai/Vendor2/Gemini-3-flash routed through
# GpuGeek (api.gpugeek.com), reasoning effort high.
#
# Mirrors scripts/launch_swebench_volatile30_no_diagnose.sh one-for-one EXCEPT
# the solver model wiring:
#   model      openai/deepseek-v4-flash         -> openai/Vendor2/Gemini-3-flash
#   base-url   https://api.deepseek.com/v1      -> https://api.gpugeek.com/v1
#   api-key    DEEPSEEK_API_KEY                 -> SOLVER_API_KEY_ENV (the gpugeek key)
#   max-tokens 4096                             -> 8192 (gemini reasoning headroom)
#   + reasoning-effort high (forwarded as model.model_kwargs.reasoning_effort=high)
#
# The proposer side is unchanged: claude deepseek-v4-pro[1m] at max effort.
# The training set (data/swebench_train_volatile30.json) and all eval/selection
# knobs are identical so candidates stay comparable to the DeepSeek run.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -z "${SOLVER_API_KEY_ENV:-}" ]; then
  echo "error: SOLVER_API_KEY_ENV not set in .env (the gpugeek solver key)" >&2; exit 1
fi
if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "error: OPENAI_API_KEY not set; needed for trace_similar embeddings (OpenAI official text-embedding-3-small)" >&2; exit 1
fi

# trace_similar MCP tool's lazy diff embedding -> OpenAI official text-embedding-3-small.
unset OPENAI_BASE_URL DIFF_EMBEDDING_MODEL

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-30}"
SPLIT="${SPLIT:-train}"
LIMIT="${LIMIT:-30}"
DATA_PATH="${DATA_PATH:-data/swebench_train_volatile30.json}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

# Use WorldCalib's own runner (the old MemoMemo path no longer exists).
MINISWE_RUNNER="${MINISWE_RUNNER:-$(pwd)/scripts/run_miniswe_swebench_single.py}"
# Hardcoded, NOT env-overridable: .env exports SOLVER_MODEL / SOLVER_BASE_URL
# for other runs, and `set -a; source .env` would otherwise clobber these and
# silently swap the solver model. This launcher's identity IS Gemini-3-flash.
SOLVER_MODEL="openai/Vendor2/Gemini-3-flash"
SOLVER_BASE_URL="https://api.gpugeek.com/v1"
SOLVER_MAX_TOKENS="${SOLVER_MAX_TOKENS:-8192}"
SOLVER_REASONING_EFFORT="${SOLVER_REASONING_EFFORT:-high}"
SOLVER_TEMPERATURE="${SOLVER_TEMPERATURE:-1}"
EVAL_WORKERS="${EVAL_WORKERS:-10}"

MINISWE_RUN_CMD="python ${MINISWE_RUNNER} run --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir} --model ${SOLVER_MODEL} --base-url ${SOLVER_BASE_URL} --max-tokens ${SOLVER_MAX_TOKENS} --temperature ${SOLVER_TEMPERATURE} --reasoning-effort ${SOLVER_REASONING_EFFORT} --api-key-env SOLVER_API_KEY_ENV"
MINISWE_EVAL_CMD="python ${MINISWE_RUNNER} eval --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir}"

run_id="${RUN_ID:-swebench_miniswe_gemini3flash_claudecode_deepseek_v4_pro_maxeffort_optimal1_no_diagnose_volatile30_${TS}}"
mkdir -p logs runs
log_path="logs/${run_id}.log"
status_file="logs/launch_${run_id}.status"
: > "$status_file"
if [ -d "runs/${run_id}" ]; then
  echo "runs/${run_id} already exists; refusing to clobber" >&2; exit 1
fi

printf '[%s] START %s\n[%s] LOG   %s\n' "$(date -Is)" "$run_id" "$(date -Is)" "$log_path" >> "$status_file"

setsid nohup python -m worldcalib.optimize_cli optimize \
  --swebench \
  --run-id "$run_id" \
  --iterations "$ITERATIONS" \
  --split "$SPLIT" \
  --limit "$LIMIT" \
  --swebench-data-path "$DATA_PATH" \
  --eval-timeout-s 900 \
  --eval-workers "$EVAL_WORKERS" \
  --proposer-agent claude \
  --claude-model 'deepseek-v4-pro[1m]' \
  --claude-effort max \
  --proposer-sandbox docker \
  --proposer-docker-image docker-claude:latest \
  --proposer-docker-user "$DOCKER_USER_SPEC" \
  --proposer-docker-home /tmp \
  --selection-policy pareto \
  --mini-swe-agent-command "$MINISWE_RUN_CMD" \
  --mini-swe-agent-eval-command "$MINISWE_EVAL_CMD" \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
printf '%s %s %s\n' "$pid" "$run_id" "$log_path"
printf 'status: %s\n' "$status_file"
