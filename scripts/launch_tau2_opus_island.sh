#!/usr/bin/env bash
# WorldCalib launcher: tau2-bench banking_knowledge, WMC-vs-noWMC comparison,
# with a REAL Claude Opus 4.8 proposer (native Claude Code OAuth) and the
# `island` evolution-tree selection policy.
#
# This is a NEW control group, distinct from scripts/launch_tau2.sh (which uses
# the kimi proposer + `--selection-policy default`). It does NOT touch that
# script. Differences from launch_tau2.sh:
#   * proposer = real Opus 4.8 via Claude Code native OAuth (docker-claude:latest
#     + a per-run writable HOME holding a copy of the host's ~/.claude.json and
#     ~/.claude/.credentials.json). NO kimi base-url/auth-token, no ANTHROPIC_*
#     model overrides.
#   * --selection-policy island (UCB1 over the iteration evolution tree, with the
#     child-replaces-parent leader rule; --island-explore-c controls explore).
#
# Both arms (calib + nowmc) launch CONCURRENTLY by default, sharing one frozen
# iter-0 seed so they start byte-identical at iter 0 and diverge only by the
# calibration treatment. tau2 eval is in-process: agent + user are both
# deepseek-chat over litellm (official api.deepseek.com, DEEPSEEK_API_KEY).
#
# Usage (from repo root):
#   scripts/launch_tau2_opus_island.sh                # both arms, shared seed
#   ARMS=calib scripts/launch_tau2_opus_island.sh     # one arm only
#   SEED_FROM=runs/trainscore_tau2_banking_knowledge scripts/launch_tau2_opus_island.sh
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Native Claude OAuth must not be hijacked by a kimi/deepseek anthropic shim.
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ANTHROPIC_MODEL \
      ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL \
      ANTHROPIC_DEFAULT_HAIKU_MODEL CLAUDE_CODE_SUBAGENT_MODEL
unset OPENAI_BASE_URL DIFF_EMBEDDING_MODEL

# DEEPSEEK_API_KEY drives the in-process tau2 eval (agent + user models).
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  printf 'fatal: DEEPSEEK_API_KEY is not set (needed for tau2 eval).\n' >&2
  exit 2
fi

# Native OAuth credential files on the host (copied per-run into the container).
for f in /data/home/yuhan/.claude.json /data/home/yuhan/.claude/.credentials.json; do
  if [ ! -f "$f" ]; then
    printf 'fatal: native-auth credential file missing: %q\n' "$f" >&2
    exit 2
  fi
done

# tau2 eval venv (worldcalib + tau2 installed, NO agentrl).
TAU2_PY="${TAU2_PY:-.venv-tau2-eval/bin/python}"
if [ ! -x "$TAU2_PY" ]; then
  printf 'fatal: tau2 venv python not found at %q\n' "$TAU2_PY" >&2
  exit 2
fi

export ENABLE_TOOL_SEARCH=false

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-20}"
# ~1.5h per-iteration proposer budget.
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

CLAUDE_MODEL="${CLAUDE_MODEL:-claude-opus-4-8}"
CLAUDE_EFFORT="${CLAUDE_EFFORT:-max}"
ISLAND_EXPLORE_C="${ISLAND_EXPLORE_C:-0.5}"

# tau2 eval config. banking_knowledge has no named splits -> deterministic
# ordinal slice (train = first TRAIN_SIZE, test = next TEST_SIZE); 97 tasks total.
TAU2_DOMAIN="${TAU2_DOMAIN:-banking_knowledge}"
TAU2_AGENT_MODEL="${TAU2_AGENT_MODEL:-deepseek/deepseek-chat}"
TAU2_USER_MODEL="${TAU2_USER_MODEL:-deepseek/deepseek-chat}"
TAU2_TRAIN_SIZE="${TAU2_TRAIN_SIZE:-30}"
TAU2_TEST_SIZE="${TAU2_TEST_SIZE:-67}"
TAU2_CONCURRENCY="${TAU2_CONCURRENCY:-32}"
TAU2_RUNS="${TAU2_RUNS:-1}"

# Shared iter-0 seed: clone its full candidate_results (with per-task tasks[] +
# traces) into each arm and continue from iter 1 via --skip-scaffold-eval.
SEED_FROM="${SEED_FROM:-runs/trainscore_tau2_banking_knowledge}"

ARMS="${ARMS:-${1:-calib,nowmc}}"

DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs
status_file="logs/launch_tau2_opus_island_${TS}.status"
: > "$status_file"

contains() { case ",$1," in *",$2,"*) return 0;; *) return 1;; esac; }

prepare_proposer_home() {
  # Claude native OAuth needs a writable HOME in the container. Mounting the
  # host ~/.claude read-only fails (Claude writes session/plugin state);
  # read-write would pollute the host login. Use an isolated per-run writable
  # copy of the minimum OAuth files instead. The optimizer re-syncs
  # .credentials.json before every attempt (handles token rotation).
  local run_id="$1"
  local stage="/tmp/worldcalib_native_proposer_${run_id}"
  rm -rf "$stage"
  mkdir -p "$stage/.claude"
  cp /data/home/yuhan/.claude.json "$stage/.claude.json"
  cp /data/home/yuhan/.claude/.credentials.json "$stage/.claude/.credentials.json"
  chmod 600 "$stage/.claude.json" "$stage/.claude/.credentials.json"
  printf '%s' "$stage"
}

start_one() {
  local variant="$1"
  case "$variant" in
    calib|nowmc) ;;
    *) printf '[%s] SKIP unknown_variant=%s\n' "$(date -Is)" "$variant" >> "$status_file"; return 0 ;;
  esac

  local run_id="tau2_${TAU2_DOMAIN}_opus48_island_maxeffort_${variant}_iter${ITERATIONS}_${TS}"
  if [ -d "runs/${run_id}" ]; then
    printf '[%s] SKIP %s existing_run_dir\n' "$(date -Is)" "$run_id" >> "$status_file"
    return 0
  fi

  # Clone the shared iter-0 seed into this arm and continue from iter 1.
  local seed_arg=()
  if [ -n "$SEED_FROM" ]; then
    if [ ! -d "$SEED_FROM/candidate_results" ]; then
      printf '[%s] FATAL %s SEED_FROM=%s has no candidate_results/\n' \
        "$(date -Is)" "$run_id" "$SEED_FROM" >> "$status_file"
      return 1
    fi
    mkdir -p "runs/${run_id}"
    cp -a "$SEED_FROM"/. "runs/${run_id}/"
    rm -f "runs/${run_id}/optimizer_summary.json" "runs/${run_id}/run_summary.json"
    seed_arg=(--skip-scaffold-eval)
  fi

  local stage_home log_path pid
  stage_home="$(prepare_proposer_home "$run_id")"
  log_path="logs/${run_id}.log"

  printf '[%s] START %s variant=%s policy=island model=%s seed_from=%s\n[%s] LOG   %s\n' \
    "$(date -Is)" "$run_id" "$variant" "$CLAUDE_MODEL" "${SEED_FROM:-<self-eval>}" \
    "$(date -Is)" "$log_path" >> "$status_file"

  setsid "$TAU2_PY" -m worldcalib.optimize_cli \
    --tau2 \
    --tau2-domain "$TAU2_DOMAIN" \
    --tau2-agent-model "$TAU2_AGENT_MODEL" \
    --tau2-user-model "$TAU2_USER_MODEL" \
    --tau2-train-size "$TAU2_TRAIN_SIZE" \
    --tau2-test-size "$TAU2_TEST_SIZE" \
    --tau2-concurrency "$TAU2_CONCURRENCY" \
    --tau2-runs "$TAU2_RUNS" \
    --proposer-variant "$variant" \
    "${seed_arg[@]}" \
    --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
    --selection-policy island \
    --island-explore-c "$ISLAND_EXPLORE_C" \
    --no-summary \
    --run-id "$run_id" \
    --out "runs/${run_id}" \
    --iterations "$ITERATIONS" \
    --split train \
    --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
    --proposer-agent claude \
    --claude-native-auth \
    --claude-model "$CLAUDE_MODEL" \
    --claude-effort "$CLAUDE_EFFORT" \
    --proposer-sandbox docker \
    --proposer-docker-image docker-claude:latest \
    --proposer-docker-user "$DOCKER_USER_SPEC" \
    --proposer-docker-home /home/yuhan \
    --proposer-docker-mount "${stage_home}:/home/yuhan:rw" \
    --proposer-docker-env ENABLE_TOOL_SEARCH \
    > "$log_path" 2>&1 < /dev/null &

  pid=$!
  printf '[%s] PID   %s %s\n' "$(date -Is)" "$run_id" "$pid" >> "$status_file"
  echo "$pid" > "logs/${run_id}.pid"
  printf 'started pid=%s run_id=%s variant=%s\n  log: %s\n' "$pid" "$run_id" "$variant" "$log_path"
}

for variant in calib nowmc; do
  contains "$ARMS" "$variant" || continue
  start_one "$variant"
done

printf '\nstatus: %s\n' "$status_file"
