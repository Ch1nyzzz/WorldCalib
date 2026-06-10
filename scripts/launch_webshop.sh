#!/usr/bin/env bash
# WorldCalib launcher: AgentBench webshop, WMC-vs-noWMC comparison.
#
# One parameterized script for both arms of the ablation. The first positional
# arg (or $VARIANT) selects the proposer variant:
#   calib  -> prose WMC + two-sided per-episode prediction, self-graded after
#             eval (self-distill, no external critic, no gate). Routes to the
#             webshop_calib skill.
#   nowmc  -> the no-WMC ablation: zero calibration, pure-default contract.
#             Routes to the webshop_nowmc skill.
# Both arms iterate the SAME frozen split (data/agentic/webshop_split.json,
# 30 train / 170 test) so the comparison is on identical episodes.
#
# Target eval model is served over the SAME OpenAI-compatible endpoint as the
# reasoning (ARC) and memory (locomo/lme) launchers: deepseek-v4-flash over
# https://api.deepseek.com. (Those launchers pass `--api-key EMPTY` and let the
# worldcalib OpenAI client fall back to DEEPSEEK_API_KEY from env; the AgentBench
# agentrl client uses the literal key, so we pass the real DEEPSEEK_API_KEY here.)
# Proposer is kimi via docker-claude-kimi, ~1.5h per-iteration budget.
#
# Usage:
#   scripts/launch_webshop.sh calib
#   scripts/launch_webshop.sh nowmc
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
EVAL_WORKERS="${EVAL_WORKERS:-24}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-300}"
# ~1.5h per-iteration proposer budget.
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

# Shared iter-0 seed: when SEED_FROM points at a precomputed iter-0 run dir, its
# full iter-0 state (candidate_results WITH per-episode tasks[], traces, ledger)
# is CLONED into this arm's run dir and the arm continues from iter 1 via
# --skip-scaffold-eval. Both arms cloning the same SEED_FROM start byte-identical
# at iter 0 — same passrate AND same per-episode evidence the calib proposer
# self-grades against — so they diverge only by the calibration treatment from
# iter 1 on. (--baseline-dir is NOT used: it loads only the summary, leaving the
# arm's candidate_results/ empty, which blinds the per-episode self-grading.)
# Build the seed once with `ITERATIONS=0 scripts/launch_webshop.sh nowmc`
# (iter 0 is treatment-agnostic).
SEED_FROM="${SEED_FROM:-}"

# AgentBench task (webshop by default; e.g. os, db, alfworld) + controller. The
# matching worker must be resident; the frozen split data/agentic/<task>_split.json
# and the shared seed both follow the task.
AGENTBENCH_TASK="${AGENTBENCH_TASK:-webshop}"
CONTROLLER_URL="${CONTROLLER_URL:-http://localhost:5020/api}"
# Frozen split owns the episode counts; sizes are passed for parity only.
AGENTBENCH_TRAIN_SIZE="${AGENTBENCH_TRAIN_SIZE:-30}"
AGENTBENCH_TEST_SIZE="${AGENTBENCH_TEST_SIZE:-170}"
AGENTBENCH_CONCURRENCY="${AGENTBENCH_CONCURRENCY:-24}"
AGENTBENCH_RUNS="${AGENTBENCH_RUNS:-1}"

# Served target model used by the webshop episodes (function-calling), over the
# same OpenAI-compatible endpoint as the ARC / locomo / lme launchers.
TARGET_MODEL="${TARGET_MODEL:-deepseek-v4-flash}"
TARGET_BASE_URL="${TARGET_BASE_URL:-https://api.deepseek.com}"
TARGET_API_KEY="${TARGET_API_KEY:-$DEEPSEEK_API_KEY}"

DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs

run_id="${AGENTBENCH_TASK}_claudekimi_k26_maxeffort_target_${TARGET_MODEL//[^A-Za-z0-9]/_}_${VARIANT}_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"
status_file="logs/launch_${AGENTBENCH_TASK}_${VARIANT}_${TS}.status"

# Clone the shared iter-0 seed into this arm and continue from iter 1.
SEED_ARG=()
if [ -n "$SEED_FROM" ]; then
  if [ ! -d "$SEED_FROM/candidate_results" ]; then
    printf 'fatal: SEED_FROM=%q has no candidate_results/ (not an iter-0 run dir)\n' "$SEED_FROM" >&2
    exit 2
  fi
  mkdir -p "runs/${run_id}"
  cp -a "$SEED_FROM"/. "runs/${run_id}/"
  # The cloned ledger/summaries belong to the seed run; drop the run-scoped
  # ones the arm will rewrite, but KEEP candidate_results/ + traces/ (the
  # iter-0 evidence) and runstore.db (the trace/eval ledger).
  rm -f "runs/${run_id}/optimizer_summary.json" "runs/${run_id}/run_summary.json"
  SEED_ARG=(--skip-scaffold-eval)
fi

printf '[%s] START %s variant=%s iter=%s seed_from=%s\n[%s] LOG %s\n' \
  "$(date -Is)" "$run_id" "$VARIANT" "$ITERATIONS" "${SEED_FROM:-<self-eval>}" "$(date -Is)" "$log_path" \
  | tee "$status_file"

setsid python -m worldcalib.optimize_cli \
  --agentbench \
  --agentbench-task "$AGENTBENCH_TASK" \
  --controller-url "$CONTROLLER_URL" \
  --proposer-variant "$VARIANT" \
  "${SEED_ARG[@]}" \
  --dry-run-probe-k "${DRY_RUN_PROBE_K:-3}" \
  --selection-policy default \
  --no-summary \
  --run-id "$run_id" \
  --out "runs/${run_id}" \
  --iterations "$ITERATIONS" \
  --split train \
  --eval-workers "$EVAL_WORKERS" \
  --eval-timeout-s "$EVAL_TIMEOUT_S" \
  --propose-timeout-s "$PROPOSE_TIMEOUT_S" \
  --model "$TARGET_MODEL" \
  --base-url "$TARGET_BASE_URL" \
  --api-key "$TARGET_API_KEY" \
  --agentbench-train-size "$AGENTBENCH_TRAIN_SIZE" \
  --agentbench-test-size "$AGENTBENCH_TEST_SIZE" \
  --agentbench-concurrency "$AGENTBENCH_CONCURRENCY" \
  --agentbench-runs "$AGENTBENCH_RUNS" \
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
printf 'started pid=%s run_id=%s variant=%s\nlog: %s\n' "$pid" "$run_id" "$VARIANT" "$log_path"
