#!/usr/bin/env bash
# Codex (gpt-5.5, reasoning_effort=high) proposer × SWE-bench mini-swe-agent
# (DeepSeek-V4-Pro via DeepSeek official OpenAI-compatible API),
# default-vs-organized on volatile30, 20 iters each, both arms parallel and
# sharing a primed iter-0 baseline.
#
# Re-launch of the cancelled minimax run after the eval-gate lockdown:
#   - eval_command tokens are rewritten to the absolute repo-root path
#   - the in-snapshot scripts/run_miniswe_swebench_single.py is mirrored from
#     the trusted copy on every iteration's snapshot build
#   - candidate validation sha256-compares the in-snapshot copy and writes
#     reward_hack_attempt=True to candidate_score_table when it differs.
#     A re-mirror happens immediately after detection so the next curaii
#     parent-copy inherits the trusted version.
# Only intentional change versus the old minimax launcher: proposer stays
# codex(gpt-5.5), the eval base model becomes deepseek-v4-pro.
#
# Auth: `codex login status` must report ChatGPT login.
#       DEEPSEEK_API_KEY must be in .env for the SWE-bench solver.
#       OPENAI_API_KEY may remain set for optional trace embeddings; it is not
#       used for mini-SWE-agent solver calls.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "error: DEEPSEEK_API_KEY not set in .env" >&2
  exit 1
fi

# The mini-SWE-agent solver receives DEEPSEEK_API_KEY through --api-key-env.
# trace_similar / RunStore trace embeddings use OpenAI official
# text-embedding-3-small (DiffEmbedder's DEFAULT_MODEL, picked up from
# OPENAI_API_KEY in .env).
if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "error: OPENAI_API_KEY not set; needed for trace_similar embeddings (OpenAI official text-embedding-3-small)" >&2
  exit 1
fi
unset OPENAI_BASE_URL DIFF_EMBEDDING_MODEL

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-20}"
ARMS="${ARMS:-default,organized}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_REASONING_EFFORT="${CODEX_REASONING_EFFORT:-high}"
SWE_LIMIT="${SWE_LIMIT:-30}"
SWE_DATA_PATH="${SWE_DATA_PATH:-data/swebench_train_volatile30.json}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-900}"
EVAL_WORKERS="${EVAL_WORKERS:-16}"
EVAL_MODEL="${EVAL_MODEL:-openai/deepseek-v4-pro}"
EVAL_BASE_URL="${EVAL_BASE_URL:-https://api.deepseek.com}"
MINISWE_MAX_TOKENS="${MINISWE_MAX_TOKENS:-4096}"
BASELINE_SWE_DIR="${BASELINE_SWE_DIR:-runs/baseline_swebench_volatile30_miniswe_deepseek_official_v4_pro_${TS}}"

mkdir -p logs runs
status_file="logs/launch_codex_gpt55_swebench_deepseek_official_v4_pro_default_vs_organized_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s arms=%s eval_model=%s\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "$ARMS" "$EVAL_MODEL" >> "$status_file"
printf '[%s] BASELINE_SWE_DIR=%s\n' "$(date -Is)" "$BASELINE_SWE_DIR" >> "$status_file"

contains() { case ",$1," in *",$2,"*) return 0;; *) return 1;; esac; }

# Shared scaffold-eval CLI fragment. The eval command still names the
# relative scripts/... path; swebench.py rewrites that to the absolute
# repo-root copy before invoking the subprocess (A1 defense).
miniswe_args=(
  --mini-swe-agent-command "python scripts/run_miniswe_swebench_single.py run --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir} --model $EVAL_MODEL --base-url $EVAL_BASE_URL --max-tokens $MINISWE_MAX_TOKENS --api-key-env DEEPSEEK_API_KEY"
  --mini-swe-agent-eval-command "python scripts/run_miniswe_swebench_single.py eval --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir}"
)

prime_swebench_baseline() {
  if [ -f "${BASELINE_SWE_DIR}/run_summary.json" ]; then
    printf '[%s] BASELINE_REUSE swebench=%s\n' "$(date -Is)" "$BASELINE_SWE_DIR" >> "$status_file"
    return 0
  fi
  printf '[%s] BASELINE_PRIME swebench -> %s\n' "$(date -Is)" "$BASELINE_SWE_DIR" >> "$status_file"
  local prime_log="logs/baseline_swebench_${TS}.log"
  python -m worldcalib.optimize_cli optimize \
    --swebench \
    --run-id "$(basename "$BASELINE_SWE_DIR")" \
    --out "$BASELINE_SWE_DIR" \
    --iterations 0 \
    --split train \
    --limit "$SWE_LIMIT" \
    --swebench-data-path "$SWE_DATA_PATH" \
    --eval-timeout-s "$EVAL_TIMEOUT_S" \
    --eval-workers "$EVAL_WORKERS" \
    --selection-policy default \
    "${miniswe_args[@]}" \
    --proposer-agent codex \
    --codex-model "$CODEX_MODEL" \
    --codex-reasoning-effort "$CODEX_REASONING_EFFORT" \
    --no-test-frontier \
    > "$prime_log" 2>&1
  local rc=$?
  if [ "$rc" -ne 0 ] || [ ! -f "${BASELINE_SWE_DIR}/run_summary.json" ]; then
    printf '[%s] BASELINE_PRIME_FAIL swebench rc=%s log=%s\n' "$(date -Is)" "$rc" "$prime_log" >> "$status_file"
    return 1
  fi
  printf '[%s] BASELINE_PRIME_DONE swebench\n' "$(date -Is)" >> "$status_file"
}

prime_swebench_baseline || exit 1

start_one() {
  local arm="$1"
  local arm_args=() run_id log_path
  if [ "$arm" = "default" ]; then
    arm_args=(--selection-policy default)
    run_id="swebench_miniswe_deepseek_official_v4_pro_codex_gpt55_pure_default_volatile30_${TS}"
  elif [ "$arm" = "organized" ]; then
    arm_args=(--selection-policy default --organized)
    run_id="swebench_miniswe_deepseek_official_v4_pro_codex_gpt55_organized_volatile30_${TS}"
  elif [ "$arm" = "nosummary" ]; then
    # combo 2: default mode, no summary at all (withhold the upstream-2 files)
    arm_args=(--selection-policy default --no-summary)
    run_id="swebench_miniswe_deepseek_official_v4_pro_codex_gpt55_nosummary_volatile30_${TS}"
  else
    printf '[%s] SKIP unknown_arm=%s\n' "$(date -Is)" "$arm" >> "$status_file"
    return 0
  fi

  if [ -d "runs/${run_id}" ]; then
    printf '[%s] SKIP %s existing_run_dir\n' "$(date -Is)" "$run_id" >> "$status_file"
    return 0
  fi

  log_path="logs/${run_id}.log"
  printf '[%s] START %s baseline=%s\n[%s] LOG   %s\n' \
    "$(date -Is)" "$run_id" "$BASELINE_SWE_DIR" "$(date -Is)" "$log_path" >> "$status_file"

  setsid nohup python -m worldcalib.optimize_cli optimize \
    --swebench \
    --run-id "$run_id" \
    --iterations "$ITERATIONS" \
    --split train \
    --limit "$SWE_LIMIT" \
    --swebench-data-path "$SWE_DATA_PATH" \
    --baseline-dir "$BASELINE_SWE_DIR" \
    --eval-timeout-s "$EVAL_TIMEOUT_S" \
    --eval-workers "$EVAL_WORKERS" \
    "${arm_args[@]}" \
    "${miniswe_args[@]}" \
    --proposer-agent codex \
    --codex-model "$CODEX_MODEL" \
    --codex-reasoning-effort "$CODEX_REASONING_EFFORT" \
    > "$log_path" 2>&1 < /dev/null &

  local pid=$!
  printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
}

for arm in default organized nosummary; do
  contains "$ARMS" "$arm" || continue
  start_one "$arm"
done

printf '[%s] LAUNCHER done — see %s\n' "$(date -Is)" "$status_file" >> "$status_file"
printf '\nstatus: %s\n' "$status_file"
