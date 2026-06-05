#!/usr/bin/env bash
# Formal SWE-bench optimization on the re-cut Gemini train set
# (data/swebench_train_gemini40_pr040.json, 40 instances, baseline ~0.40).
#
#   solver   : Gemini-3-flash @ GpuGeek (temp 1, reasoning high, 8192)  [held fixed]
#   proposer : Claude Opus 4.8 NATIVE auth (subscription OAuth), effort high
#   arms     : default vs organized(no-state.md) — BOTH --no-summary
#
# Flow (mirrors the terminus default-vs-organized launcher):
#   1. Prime a Gemini baseline (--iterations 0) on the 40-instance train split.
#      Synchronous; both arms share it via --baseline-dir so candidates stay
#      comparable to the same base.
#   2. Launch default + organized(no-state) arms in the background, N iters each.
#
# Opus 4.8 proposer runs in docker-claude:latest with the user's ~/.claude
# credentials mounted read-only (native subscription OAuth; ANTHROPIC_* are
# stripped by --claude-native-auth). Home MUST be /home/yuhan (not /tmp) so the
# mounted .credentials.json is found.
#
# Embeddings for organized's trace_similar tool go through OpenAI official
# text-embedding-3-small (needs OPENAI_API_KEY; OPENAI_BASE_URL/DIFF_EMBEDDING_MODEL
# unset so the openai SDK hits api.openai.com with the default model).
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
  echo "error: OPENAI_API_KEY not set; needed for organized trace_similar embeddings" >&2; exit 1
fi
if [ ! -f /data/home/yuhan/.claude/.credentials.json ]; then
  echo "error: /data/home/yuhan/.claude/.credentials.json missing (Opus native auth needs it)" >&2; exit 1
fi

# trace_similar embeddings -> OpenAI official text-embedding-3-small
unset OPENAI_BASE_URL DIFF_EMBEDDING_MODEL

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-20}"
EVAL_WORKERS="${EVAL_WORKERS:-24}"
DATA_PATH="${DATA_PATH:-data/swebench_train_gemini30_pr040.json}"
LIMIT="${LIMIT:-30}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"
# Optional pre-built baseline run dir (hand-assembled from existing traces).
# When set, Step 1 skips the live prime and both arms point --baseline-dir here.
# It MUST be a run dir with run_summary.json (split=train) whose candidate
# count equals LIMIT.
PREBUILT_BASELINE="${PREBUILT_BASELINE:-}"

# --- Gemini-3-flash solver (hardcoded; .env's SOLVER_MODEL/BASE_URL would clobber) ---
MINISWE_RUNNER="${MINISWE_RUNNER:-$(pwd)/scripts/run_miniswe_swebench_single.py}"
SOLVER_MODEL="openai/Vendor2/Gemini-3-flash"
SOLVER_BASE_URL="https://api.gpugeek.com/v1"
SOLVER_MAX_TOKENS="${SOLVER_MAX_TOKENS:-8192}"
SOLVER_TEMPERATURE="${SOLVER_TEMPERATURE:-1}"
SOLVER_REASONING_EFFORT="${SOLVER_REASONING_EFFORT:-high}"
MINISWE_RUN_CMD="python ${MINISWE_RUNNER} run --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir} --model ${SOLVER_MODEL} --base-url ${SOLVER_BASE_URL} --max-tokens ${SOLVER_MAX_TOKENS} --temperature ${SOLVER_TEMPERATURE} --reasoning-effort ${SOLVER_REASONING_EFFORT} --api-key-env SOLVER_API_KEY_ENV"
MINISWE_EVAL_CMD="python ${MINISWE_RUNNER} eval --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir}"

BASE_RUN="swebench_gemini30_opus_baseline_${TS}"
DEF_RUN="${DEF_RUN_ID:-swebench_gemini30_opus_high_default_nosummary_${TS}}"
ORG_RUN="${ORG_RUN_ID:-swebench_gemini30_opus_high_organized_nosummary_nostate_${TS}}"
# RESUME=1 continues existing DEF_RUN_ID/ORG_RUN_ID runs from their last
# completed iteration (adds --resume) and appends to their logs.
RESUME="${RESUME:-}"
resume_flag=(); redir=">"
if [ -n "$RESUME" ]; then resume_flag=(--resume); fi
mkdir -p logs runs
status="logs/launch_swebench_gemini30_opus_${TS}.status"
: > "$status"
log() { printf '[%s] %s\n' "$(date -Is)" "$*" | tee -a "$status"; }

# Shared args (identical across baseline + both arms except evidence-mode flags).
COMMON=(
  --swebench
  --split train --limit "$LIMIT"
  --swebench-data-path "$DATA_PATH"
  --eval-timeout-s 900
  --eval-workers "$EVAL_WORKERS"
  --mini-swe-agent-command "$MINISWE_RUN_CMD"
  --mini-swe-agent-eval-command "$MINISWE_EVAL_CMD"
  --proposer-agent claude
  --claude-native-auth
  --claude-model claude-opus-4-8
  --claude-effort high
  --proposer-sandbox docker
  --proposer-docker-image docker-claude:latest
  --proposer-docker-user "$DOCKER_USER_SPEC"
  --proposer-docker-home /home/yuhan
  --proposer-docker-mount /data/home/yuhan/.claude:/home/yuhan/.claude:ro
  --proposer-docker-mount /data/home/yuhan/.claude.json:/home/yuhan/.claude.json:ro
  --selection-policy pareto
)

log "LAUNCHER start ts=$TS proposer=opus-4.8(native,high) solver=$SOLVER_MODEL data=$DATA_PATH iters=$ITERATIONS workers=$EVAL_WORKERS"

# ---- Step 1: establish the shared baseline ----
if [ -n "$PREBUILT_BASELINE" ]; then
  # Hand-assembled baseline (reused traces) — skip the live prime entirely.
  if [ ! -f "${PREBUILT_BASELINE%/}/run_summary.json" ]; then
    log "PREBUILT_BASELINE_MISSING ${PREBUILT_BASELINE}/run_summary.json — aborting"
    exit 1
  fi
  BASELINE_PATH="${PREBUILT_BASELINE%/}"
  log "BASELINE_PREBUILT -> $BASELINE_PATH (skip prime)"
elif [ -f "runs/${BASE_RUN}/run_summary.json" ]; then
  BASELINE_PATH="runs/${BASE_RUN}"
  log "BASELINE_REUSE $BASE_RUN"
else
  log "BASELINE_PRIME -> $BASE_RUN (log: logs/${BASE_RUN}.log)"
  python -m worldcalib.optimize_cli optimize \
    "${COMMON[@]}" \
    --iterations 0 \
    --run-id "$BASE_RUN" \
    > "logs/${BASE_RUN}.log" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ] || [ ! -f "runs/${BASE_RUN}/run_summary.json" ]; then
    log "BASELINE_PRIME_FAIL rc=$rc — aborting, NOT launching arms. See logs/${BASE_RUN}.log"
    exit 1
  fi
  BASELINE_PATH="runs/${BASE_RUN}"
  log "BASELINE_PRIME_DONE $BASE_RUN"
fi

# ---- Step 2: launch default + organized arms (background) ----
log "START default -> $DEF_RUN (log: logs/${DEF_RUN}.log)"
setsid nohup python -m worldcalib.optimize_cli optimize \
  "${COMMON[@]}" \
  "${resume_flag[@]}" \
  --iterations "$ITERATIONS" \
  --no-summary \
  --baseline-dir "$BASELINE_PATH" \
  --run-id "$DEF_RUN" \
  >> "logs/${DEF_RUN}.log" 2>&1 < /dev/null &
log "PID default=$!"

log "START organized -> $ORG_RUN (log: logs/${ORG_RUN}.log)"
setsid nohup python -m worldcalib.optimize_cli optimize \
  "${COMMON[@]}" \
  "${resume_flag[@]}" \
  --iterations "$ITERATIONS" \
  --no-summary \
  --organized --organized-no-state-md \
  --baseline-dir "$BASELINE_PATH" \
  --run-id "$ORG_RUN" \
  >> "logs/${ORG_RUN}.log" 2>&1 < /dev/null &
log "PID organized=$!"

log "LAUNCHER done — arms running in background. status=$status"
printf 'baseline: runs/%s\ndefault:  runs/%s\norganized:runs/%s\nstatus:   %s\n' \
  "$BASE_RUN" "$DEF_RUN" "$ORG_RUN" "$status"
