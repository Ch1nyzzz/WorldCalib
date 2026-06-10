#!/usr/bin/env bash
# WorldCalib launcher: AutoLab terminus-2 harness optimization — DESIGNER mode.
#
# Unlike launch_autolab_calib.sh (a per-iteration loop), this runs ONE long
# autonomous designer session: the proposer owns the rhythm, edits the editable
# terminus-2 source freely, calls `worldcalib-eval` (a host-side bridge) on a
# train subset whenever it wants to verify, keeps a DESIGN_LOG.md, and
# checkpoints converged designs. After the session the harness scores every
# checkpoint on the held-out test split and picks a winner. --iterations is
# ignored; an iter0 seed frontier still runs once to establish the baseline.
#
#   proposer : PROPOSER_BACKEND=kimi-docker  -> kimi-k2.6 via claude-code in
#                                               docker-claude-kimi:latest
#              PROPOSER_BACKEND=claude-native -> Claude OAuth (Opus) in
#                                               docker-claude:latest w/ staged creds
#   solver   : terminus-2 (cyh_dev harbor venv) driving --autolab-harbor-model.
#   eval     : runs HOST-side via the eval bridge (the sandbox has no harbor).
#
# GPU tasks need the cyh_dev harbor patched (see apply_harbor_patch_cyh_dev.sh);
# set AUTOLAB_SKIP_PATCH_CHECK=1 for CPU-only subsets on an unpatched venv.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

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
  # claude-native: real Claude OAuth. Must NOT be hijacked by a kimi/deepseek shim.
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
EVAL_WORKERS="${EVAL_WORKERS:-2}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-20000}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

# Designer goal-loop. The model judges convergence (done.py) but may not stop
# until >= MIN_DIRECTIONS genuinely-different CODE-LEVEL directions are
# implemented+evaluated+checkpointed; the loop re-invokes up to MAX_ROUNDS.
# Budgets are a generous SAFETY NET (loop stops on the goal, not the quota).
DESIGNER_MIN_DIRECTIONS="${DESIGNER_MIN_DIRECTIONS:-3}"
DESIGNER_MAX_ROUNDS="${DESIGNER_MAX_ROUNDS:-6}"
DESIGNER_CONFIRM_ATTEMPTS="${DESIGNER_CONFIRM_ATTEMPTS:-2}"
DESIGNER_SESSION_TIMEOUT_S="${DESIGNER_SESSION_TIMEOUT_S:-14400}"   # 4h PER ROUND
DESIGNER_MAX_EVAL_CALLS="${DESIGNER_MAX_EVAL_CALLS:-200}"
DESIGNER_MAX_TASK_RUNS="${DESIGNER_MAX_TASK_RUNS:-600}"
DESIGNER_MAX_WALLCLOCK_S="${DESIGNER_MAX_WALLCLOCK_S:-39600}"       # 11h eval wall-clock net
DESIGNER_SMOKE_TASK_IDS="${DESIGNER_SMOKE_TASK_IDS:-}"
DESIGNER_SMOKE_SIZE="${DESIGNER_SMOKE_SIZE:-3}"

# Web search (used to research existing harness architectures) requires the
# claude-native backend (Anthropic WebSearch); kimi-docker has no web tool.
if [ "$PROPOSER_BACKEND" != "claude-native" ]; then
  printf '[warn] PROPOSER_BACKEND=%s has no web-search tool; designer works best with claude-native.\n' \
    "$PROPOSER_BACKEND" >&2
fi

# Raise the proposer sandbox's bash timeout so a `worldcalib-eval` call can BLOCK
# until the (slow) host eval finishes and then return automatically — no polling.
# The eval client waits up to WORLDCALIB_EVAL_MAX_WAIT_S, set just under the bash
# max; a rare eval that runs longer degrades gracefully to submit + --collect.
export BASH_DEFAULT_TIMEOUT_MS="${BASH_DEFAULT_TIMEOUT_MS:-7200000}"   # 120 min
export BASH_MAX_TIMEOUT_MS="${BASH_MAX_TIMEOUT_MS:-10800000}"          # 180 min
export WORLDCALIB_EVAL_MAX_WAIT_S="${WORLDCALIB_EVAL_MAX_WAIT_S:-7000}"  # ~117 min
proposer_args+=(
  --proposer-docker-env BASH_DEFAULT_TIMEOUT_MS
  --proposer-docker-env BASH_MAX_TIMEOUT_MS
  --proposer-docker-env WORLDCALIB_EVAL_MAX_WAIT_S
)

TASKS_PATH="${AUTOLAB_TASKS_PATH:-third_party/autolab/tasks}"
HARBOR_BINARY="${AUTOLAB_HARBOR_BINARY:-/data/home/yuhan/cyh_dev/bin/harbor}"
HARBOR_PYTHON="${AUTOLAB_HARBOR_PYTHON:-/data/home/yuhan/cyh_dev/bin/python}"
HARBOR_MODEL="${AUTOLAB_HARBOR_MODEL:-deepseek-v4-pro[1m]}"

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

designer_args=(
  --designer
  --designer-min-directions "$DESIGNER_MIN_DIRECTIONS"
  --designer-max-rounds "$DESIGNER_MAX_ROUNDS"
  --designer-confirm-attempts "$DESIGNER_CONFIRM_ATTEMPTS"
  --designer-session-timeout-s "$DESIGNER_SESSION_TIMEOUT_S"
  --designer-max-eval-calls "$DESIGNER_MAX_EVAL_CALLS"
  --designer-max-task-runs "$DESIGNER_MAX_TASK_RUNS"
  --designer-max-wall-clock-s "$DESIGNER_MAX_WALLCLOCK_S"
  --designer-smoke-size "$DESIGNER_SMOKE_SIZE"
)
if [ -n "$DESIGNER_SMOKE_TASK_IDS" ]; then
  designer_args+=(--designer-smoke-task-ids "$DESIGNER_SMOKE_TASK_IDS")
fi

# BASELINE_DIR: reuse an existing run's iter0 baseline instead of re-evaluating
# the seed terminus-2 on every task (saves hours). Point it at a run dir that has
# run_summary.json with the `terminus2_autolab` seed candidate; the task subset
# (AUTOLAB_TASK_IDS) MUST match that baseline's task set (count check is strict).
baseline_args=()
if [ -n "${BASELINE_DIR:-}" ]; then
  if [ ! -f "${BASELINE_DIR}/run_summary.json" ]; then
    printf 'fatal: BASELINE_DIR=%q has no run_summary.json to reuse iter0 from.\n' \
      "$BASELINE_DIR" >&2
    exit 2
  fi
  baseline_args=(--baseline-dir "$BASELINE_DIR")
fi

mkdir -p logs runs
run_id="autolab_designer_${PROPOSER_TAG}_${TS}"

# claude-native needs a per-run writable HOME holding a copy of the OAuth files.
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
status_file="logs/launch_autolab_designer_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s backend=%s solver=%s tasks=%s session_timeout=%ss\n' \
  "$(date -Is)" "$TS" "$PROPOSER_BACKEND" "$HARBOR_MODEL" "$TASKS_PATH" "$DESIGNER_SESSION_TIMEOUT_S" >> "$status_file"
printf '[%s] START %s\n[%s] LOG   %s\n' \
  "$(date -Is)" "$run_id" "$(date -Is)" "$log_path" >> "$status_file"

setsid worldcalib-optimize \
  "${autolab_args[@]}" \
  "${designer_args[@]}" \
  "${baseline_args[@]}" \
  --split train \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --api-key EMPTY \
  "${proposer_args[@]}" \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
printf 'started pid=%s run_id=%s backend=%s\nlog: %s\nstatus: %s\n' \
  "$pid" "$run_id" "$PROPOSER_BACKEND" "$log_path" "$status_file"
