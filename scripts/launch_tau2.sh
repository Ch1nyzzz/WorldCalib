#!/usr/bin/env bash
# WorldCalib launcher: tau2-bench, WMC-vs-noWMC comparison (default domain
# banking_knowledge). One parameterized script for both arms. The first
# positional arg (or $VARIANT) selects the proposer variant:
#   calib  -> prose WMC + two-sided per-task-type prediction, self-graded after
#             eval (self-distill, no external critic, no gate). Routes to the
#             tau2_calib skill.
#   nowmc  -> the no-WMC ablation: zero calibration, pure-default contract.
#             Routes to the tau2_nowmc skill.
#
# tau2 runs FROM the tau2 eval venv (.venv-tau2-eval, agentrl-free). The eval is
# in-process: agent + user are both deepseek-chat over litellm (official
# api.deepseek.com, DEEPSEEK_API_KEY from env) — there is no controller/worker
# and no --model/--base-url/--api-key (those are unused by the tau2 backend).
# The proposer is kimi via docker-claude-kimi, ~1.5h per-iteration budget,
# identical to the agentbench launchers.
#
# Shared iter-0 seed: SEED_FROM clones a precomputed iter-0 run dir (full
# candidate_results WITH per-task tasks[] + traces) into this arm's run dir and
# continues from iter 1 via --skip-scaffold-eval, so both arms start byte-
# identical at iter 0 and diverge only by the calibration treatment.
#
# Usage (from repo root):
#   SEED_FROM=runs/trainscore_tau2_banking_knowledge scripts/launch_tau2.sh calib
#   SEED_FROM=runs/trainscore_tau2_banking_knowledge scripts/launch_tau2.sh nowmc
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

for v in KIMI_API_KEY DEEPSEEK_API_KEY; do
  if [ -z "${!v:-}" ]; then
    printf 'fatal: %s is not set.\n' "$v" >&2
    exit 2
  fi
done

# tau2 eval venv (must have worldcalib + tau2 installed, NO agentrl).
TAU2_PY="${TAU2_PY:-.venv-tau2-eval/bin/python}"
if [ ! -x "$TAU2_PY" ]; then
  printf 'fatal: tau2 venv python not found at %q\n' "$TAU2_PY" >&2
  exit 2
fi

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
ITERATIONS="${ITERATIONS:-20}"
# ~1.5h per-iteration proposer budget.
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

# tau2 eval config. banking_knowledge has no named splits → deterministic
# ordinal slice (train = first TRAIN_SIZE tasks, test = next TEST_SIZE); both
# arms get identical data without a frozen file. 97 tasks total.
TAU2_DOMAIN="${TAU2_DOMAIN:-banking_knowledge}"
TAU2_AGENT_MODEL="${TAU2_AGENT_MODEL:-deepseek/deepseek-chat}"
TAU2_USER_MODEL="${TAU2_USER_MODEL:-deepseek/deepseek-chat}"
TAU2_TRAIN_SIZE="${TAU2_TRAIN_SIZE:-30}"
TAU2_TEST_SIZE="${TAU2_TEST_SIZE:-67}"
TAU2_CONCURRENCY="${TAU2_CONCURRENCY:-32}"
TAU2_RUNS="${TAU2_RUNS:-1}"

# Selection policy. `island` (UCB1 over the iteration evolution tree, child-
# replaces-parent leader rule) evolves each candidate from the CURRENT best
# instead of always re-baselining from the clean seed (`default`), so gains
# compound across iterations. ISLAND_EXPLORE_C tunes explore-vs-exploit.
SELECTION_POLICY="${SELECTION_POLICY:-self}"
ISLAND_EXPLORE_C="${ISLAND_EXPLORE_C:-0.5}"

# Shared iter-0 seed (see header). When set, clone it in and continue from iter 1.
SEED_FROM="${SEED_FROM:-}"

DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs

run_id="tau2_${TAU2_DOMAIN}_claudekimi_k26_maxeffort_${VARIANT}_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"
status_file="logs/launch_tau2_${VARIANT}_${TS}.status"

# Clone the shared iter-0 seed into this arm and continue from iter 1.
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

printf '[%s] START %s variant=%s domain=%s iter=%s seed_from=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "$VARIANT" "$TAU2_DOMAIN" "$ITERATIONS" "${SEED_FROM:-<self-eval>}" \
  "$(date -Is)" "$log_path" \
  | tee "$status_file"

setsid "$TAU2_PY" -m worldcalib.optimize_cli \
  --tau2 \
  --tau2-domain "$TAU2_DOMAIN" \
  --tau2-agent-model "$TAU2_AGENT_MODEL" \
  --tau2-user-model "$TAU2_USER_MODEL" \
  --tau2-train-size "$TAU2_TRAIN_SIZE" \
  --tau2-test-size "$TAU2_TEST_SIZE" \
  --tau2-concurrency "$TAU2_CONCURRENCY" \
  --tau2-runs "$TAU2_RUNS" \
  --proposer-variant "$VARIANT" \
  "${SEED_ARG[@]}" \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  --selection-policy "$SELECTION_POLICY" \
  --island-explore-c "$ISLAND_EXPLORE_C" \
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
printf 'started pid=%s run_id=%s variant=%s domain=%s\nlog: %s\n' "$pid" "$run_id" "$VARIANT" "$TAU2_DOMAIN" "$log_path"
