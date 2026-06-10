#!/usr/bin/env bash
# WorldCalib launcher: AutoLab terminus-2 harness optimization (calib / nowmc arm).
#
#   proposer : PROPOSER_BACKEND=kimi-docker  -> kimi-k2.6 via claude-code in
#                                               docker-claude-kimi:latest
#              PROPOSER_BACKEND=claude-native -> Claude OAuth (Opus) in
#                                               docker-claude:latest w/ staged creds
#   solver   : terminus-2 (cyh_dev harbor venv) driving --autolab-harbor-model;
#              for an openai/* model (e.g. openai/deepseek-v4-flash) litellm reads
#              OPENAI_API_KEY + OPENAI_BASE_URL from this env (set below).
#   surface  : the proposer edits a snapshot of the terminus-2 package (Option B,
#              loaded via --agent-import-path); see autolab_optimizer.py.
#   tasks    : AutoLab suite under third_party/autolab/tasks (subset via
#              AUTOLAB_TASK_IDS; empty = all 36).
#   variant  : calib -> autolab_calib skill (single-proposer self-distill WMC).
#
# GPU tasks need the cyh_dev harbor patched (see apply_harbor_patch_cyh_dev.sh);
# set AUTOLAB_SKIP_PATCH_CHECK=1 for CPU-only subsets on an unpatched venv.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROPOSER_VARIANT="${PROPOSER_VARIANT:-calib}"
case "$PROPOSER_VARIANT" in
  calib|nowmc) ;;
  *) printf 'fatal: PROPOSER_VARIANT must be calib or nowmc, got %q\n' "$PROPOSER_VARIANT" >&2; exit 2 ;;
esac

PROPOSER_BACKEND="${PROPOSER_BACKEND:-kimi-docker}"
case "$PROPOSER_BACKEND" in
  kimi-docker|claude-native) ;;
  *) printf 'fatal: PROPOSER_BACKEND must be kimi-docker or claude-native, got %q\n' "$PROPOSER_BACKEND" >&2; exit 2 ;;
esac

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

unset DIFF_EMBEDDING_MODEL

# Solver (terminus-2) reaches its model via litellm in the harbor HOST process.
# For openai/* models litellm reads OPENAI_API_KEY + OPENAI_BASE_URL from here —
# the seed candidate carries no api_base kwarg, so the endpoint MUST come from
# this env. Default to the deepseek endpoint (override via SOLVER_OPENAI_*).
export OPENAI_API_KEY="${SOLVER_OPENAI_API_KEY:-${DEEPSEEK_API_KEY:-${OPENAI_API_KEY:-}}}"
export OPENAI_BASE_URL="${SOLVER_OPENAI_BASE_URL:-https://api.deepseek.com}"

export ENABLE_TOOL_SEARCH=false
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

# ── proposer backend setup ────────────────────────────────────────────────────
proposer_args=()
stage_home=""
if [ "$PROPOSER_BACKEND" = "kimi-docker" ]; then
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
  export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
  export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
  export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
  export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"
  PROPOSER_TAG="claudekimi_k26"
  proposer_args=(
    --proposer-agent claude
    --claude-base-url "$KIMI_BASE_URL"
    --claude-auth-token "$KIMI_API_KEY"
    --claude-model "$KIMI_MODEL"
    --claude-effort "${CLAUDE_EFFORT:-max}"
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
else
  # claude-native: real Claude OAuth. Must NOT be hijacked by a kimi/deepseek
  # anthropic shim — unset ANTHROPIC_* (but keep OPENAI_* for the deepseek solver,
  # which only reaches the host harbor subprocess, never the proposer container).
  unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_MODEL \
        ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL \
        ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL
  for f in /data/home/yuhan/.claude.json /data/home/yuhan/.claude/.credentials.json; do
    if [ ! -f "$f" ]; then
      printf 'fatal: native-auth credential file missing: %q\n' "$f" >&2
      exit 2
    fi
  done
  CLAUDE_MODEL="${CLAUDE_MODEL:-claude-opus-4-8}"
  PROPOSER_TAG="claudenative_${CLAUDE_MODEL//[^a-zA-Z0-9]/}"
  proposer_args=(
    --proposer-agent claude
    --claude-native-auth
    --claude-model "$CLAUDE_MODEL"
    --claude-effort "${CLAUDE_EFFORT:-max}"
    --proposer-sandbox docker
    --proposer-docker-image docker-claude:latest
    --proposer-docker-user "$DOCKER_USER_SPEC"
    --proposer-docker-home /home/yuhan
    --proposer-docker-env ENABLE_TOOL_SEARCH
  )
fi

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-5}"
EVAL_WORKERS="${EVAL_WORKERS:-2}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-20000}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

TASKS_PATH="${AUTOLAB_TASKS_PATH:-third_party/autolab/tasks}"
HARBOR_BINARY="${AUTOLAB_HARBOR_BINARY:-/data/home/yuhan/cyh_dev/bin/harbor}"
HARBOR_PYTHON="${AUTOLAB_HARBOR_PYTHON:-/data/home/yuhan/cyh_dev/bin/python}"
HARBOR_MODEL="${AUTOLAB_HARBOR_MODEL:-deepseek-v4-pro[1m]}"
# harbor --env-file: feed ONLY the resolved solver creds, NOT the repo .env. The
# repo .env carries a separate OPENAI_API_KEY (often stale) that, passed verbatim,
# is loaded by harbor's litellm and OVERRIDES the deepseek key we resolved above —
# every model call then 401s and all tasks score 0. The runner already inherits the
# full .env via the process env (launcher sourced it), so a minimal solver-only
# env-file loses nothing and stops the clobber. Pin AUTOLAB_HARBOR_ENV_FILE to opt
# back into a specific file.
if [ -n "${AUTOLAB_HARBOR_ENV_FILE:-}" ]; then
  HARBOR_ENV_FILE="$AUTOLAB_HARBOR_ENV_FILE"
else
  HARBOR_ENV_FILE="/tmp/worldcalib_solver_env_${TS}.env"
  { printf 'OPENAI_API_KEY=%s\n' "$OPENAI_API_KEY"
    printf 'OPENAI_BASE_URL=%s\n' "$OPENAI_BASE_URL"; } > "$HARBOR_ENV_FILE"
  chmod 600 "$HARBOR_ENV_FILE"
fi
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

# BASELINE_DIR: reuse a precomputed iter-0 seed eval (its candidate_results/
# terminus2_autolab.json) so both ablation arms share the exact same baseline
# instead of re-paying (and re-randomising) the seed eval.
baseline_args=()
if [ -n "${BASELINE_DIR:-}" ]; then
  if [ ! -d "$BASELINE_DIR/candidate_results" ]; then
    printf 'fatal: BASELINE_DIR=%q has no candidate_results/ (not an iter-0 run dir)\n' "$BASELINE_DIR" >&2
    exit 2
  fi
  baseline_args=(--baseline-dir "$BASELINE_DIR")
fi

mkdir -p logs runs

# RESUME_RUN_ID: continue an existing run dir (e.g. after truncate_run_to_iter.py)
# instead of starting a fresh run. The optimizer derives the resume start from
# candidate_results/ (max completed iter + 1) and re-runs the rest; iter0 seed is
# reused, not re-evaluated. ITERATIONS must match the original run's target.
resume_args=()
if [ -n "${RESUME_RUN_ID:-}" ]; then
  run_id="$RESUME_RUN_ID"
  if [ ! -d "runs/${run_id}/candidate_results" ]; then
    printf 'fatal: RESUME_RUN_ID=%q has no runs/%s/candidate_results to resume from.\n' \
      "$run_id" "$run_id" >&2
    exit 2
  fi
  resume_args=(--resume)
else
  run_id="autolab_${PROPOSER_TAG}_${PROPOSER_VARIANT}_iter${ITERATIONS}_${TS}"
fi

# claude-native needs a per-run writable HOME holding a copy of the OAuth files
# (mounting ~/.claude read-only fails; read-write would pollute the host login).
if [ "$PROPOSER_BACKEND" = "claude-native" ]; then
  stage_home="/tmp/worldcalib_native_proposer_${run_id}"
  rm -rf "$stage_home"
  mkdir -p "$stage_home/.claude"
  cp /data/home/yuhan/.claude.json "$stage_home/.claude.json"
  cp /data/home/yuhan/.claude/.credentials.json "$stage_home/.claude/.credentials.json"
  chmod 600 "$stage_home/.claude.json" "$stage_home/.claude/.credentials.json"
  proposer_args+=(--proposer-docker-mount "${stage_home}:/home/yuhan:rw")
fi

log_path="logs/${run_id}.log"
status_file="logs/launch_autolab_${PROPOSER_VARIANT}_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s variant=%s backend=%s solver=%s tasks=%s\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "$PROPOSER_VARIANT" "$PROPOSER_BACKEND" "$HARBOR_MODEL" "$TASKS_PATH" >> "$status_file"
printf '[%s] START %s\n[%s] LOG   %s\n' \
  "$(date -Is)" "$run_id" "$(date -Is)" "$log_path" >> "$status_file"

setsid worldcalib-optimize \
  "${autolab_args[@]}" \
  "${baseline_args[@]}" \
  --split train \
  --proposer-variant "$PROPOSER_VARIANT" \
  --selection-policy self \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --iterations "$ITERATIONS" \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --api-key EMPTY \
  "${resume_args[@]}" \
  "${proposer_args[@]}" \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
printf 'started pid=%s run_id=%s variant=%s backend=%s\nlog: %s\nstatus: %s\n' \
  "$pid" "$run_id" "$PROPOSER_VARIANT" "$PROPOSER_BACKEND" "$log_path" "$status_file"
