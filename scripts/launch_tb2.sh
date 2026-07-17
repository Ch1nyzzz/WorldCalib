#!/usr/bin/env bash
# WorldCalib launcher: Terminal-Bench 2.0 (Harbor + editable terminus-2), WMC-vs-noWMC.
# One parameterized script for both arms; the first positional arg (or $VARIANT):
#   calib  -> self-distill WMC (no external critic). Routes to tb2_calib skill.
#   nowmc  -> the no-WMC ablation (pure-default contract). Routes to tb2_nowmc.
#
#   solver   : terminus-2 run by the cyh_dev harbor venv, driving
#              Vendor3/DeepSeek-V4-Flash on the shared GPUGeek account
#              (Solver_API_KEY) — the same endpoint/model putty's configs pin as
#              their frozen solver. The endpoint reaches terminus-2 as the
#              api_base agent kwarg (tb2_optimizer pins it on every candidate);
#              the key reaches litellm as OPENAI_API_KEY, via --env-file.
#   candidate: an editable COPY of terminus-2 (references/vendor/terminus2_agent_tb2,
#              loaded via --agent-import-path). tb2 keeps its own copy so a
#              candidate's edits never reach the AutoLab experiments.
#   tasks    : the Harbor terminal-bench 2.0 dataset; the frozen split
#              data/tb2/split.json owns the ids (20 train / 67 test), reproducing
#              putty's seeded hash-bucketing so the numbers compare.
#   scoring  : the published metric — pass@1 x TB2_REPEATS trials, MEAN-aggregated
#              per task (never max).
#   proposer : kimi via docker-claude-kimi, identical to the other launchers.
#
# Shared iter-0 seed: SEED_FROM clones a precomputed iter-0 run dir into this arm
# and continues from iter 1 via --skip-scaffold-eval, so both arms start
# byte-identical at iter 0 and diverge only by the calibration treatment. Verify
# it took, rather than trusting it:
#   md5sum runs/<seed>/candidate_results/iter000*.json \
#          runs/<arm>/candidate_results/iter000*.json
#
# Usage (from repo root):
#   ITERATIONS=0 scripts/launch_tb2.sh nowmc           # build the shared seed
#   SEED_FROM=runs/<seed_run> scripts/launch_tb2.sh calib
#   SEED_FROM=runs/<seed_run> scripts/launch_tb2.sh nowmc
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

# Main venv python (runs worldcalib + the optimizer loop). Harbor itself is a
# separate venv, reached through --tb2-harbor-binary / --tb2-harbor-python.
TB2_PY="${TB2_PY:-python}"
HARBOR_BINARY="${TB2_HARBOR_BINARY:-/data/home/yuhan/cyh_dev/bin/harbor}"
HARBOR_PYTHON="${TB2_HARBOR_PYTHON:-/data/home/yuhan/cyh_dev/bin/python}"

TB2_DATASET="${TB2_DATASET:-/data/home/yuhan/putty/runs/terminalbench_traceunit_v1/benchmark_data/terminalbench/dataset}"
TB2_MODEL="${TB2_MODEL:-Vendor3/DeepSeek-V4-Flash}"
TB2_API_BASE="${TB2_API_BASE:-${SOLVER_BASE_URL:-https://api.gpugeek.com/v1}}"
# The published methodology: pass@1 x 2 repeats, MEAN.
TB2_REPEATS="${TB2_REPEATS:-2}"
# Each concurrent trial takes its own Docker compose network and the host's
# default pool holds ~31 in total, shared with whatever else runs here. putty
# measured 16 exhausting the pool ("all predefined address pools have been fully
# subnetted") and failing 19 of 20 tasks. Keep real headroom.
TB2_CONCURRENCY="${TB2_CONCURRENCY:-8}"

if [[ "$KIMI_API_KEY" == sk-kimi-* ]]; then
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.kimi.com/coding}"
else
  KIMI_BASE_URL="${KIMI_BASE_URL:-https://api.moonshot.ai/anthropic}"
fi
KIMI_MODEL="${KIMI_MODEL:-kimi-k2.7}"

unset DIFF_EMBEDDING_MODEL
export ENABLE_TOOL_SEARCH=false
export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-20}"
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"

SELECTION_POLICY="${SELECTION_POLICY:-self}"
SEED_FROM="${SEED_FROM:-}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

mkdir -p logs runs

run_id="tb2_claudekimi_k27_maxeffort_${VARIANT}_iter${ITERATIONS}_${TS}"

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
status_file="logs/launch_tb2_${VARIANT}_${TS}.status"

# harbor --env-file: feed ONLY the resolved solver creds, never the repo .env.
# The repo .env carries its own OPENAI_API_KEY for unrelated things; passed
# verbatim it would silently authenticate the solver against the wrong account.
ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/tb2_solver_env.XXXXXX")"
trap 'rm -f "$ENV_FILE"' EXIT
{
  printf 'OPENAI_API_KEY=%s\n' "$Solver_API_KEY"
  printf 'OPENAI_BASE_URL=%s\n' "$TB2_API_BASE"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

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

setsid "$TB2_PY" -m worldcalib.optimize_cli \
  --tb2 \
  --tb2-dataset "$TB2_DATASET" \
  --tb2-harbor-binary "$HARBOR_BINARY" \
  --tb2-harbor-python "$HARBOR_PYTHON" \
  --tb2-harbor-model "$TB2_MODEL" \
  --tb2-api-base "$TB2_API_BASE" \
  --tb2-repeats "$TB2_REPEATS" \
  --tb2-concurrency "$TB2_CONCURRENCY" \
  --tb2-env-file "$ENV_FILE" \
  --proposer-variant "$VARIANT" \
  "${resume_args[@]}" \
  "${SEED_ARG[@]}" \
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
  --proposer-docker-env KIMI_API_KEY \
  --proposer-docker-env ENABLE_TOOL_SEARCH \
  --proposer-docker-env CLAUDE_CODE_SUBAGENT_MODEL \
  --proposer-docker-env ANTHROPIC_DEFAULT_OPUS_MODEL \
  --proposer-docker-env ANTHROPIC_DEFAULT_SONNET_MODEL \
  --proposer-docker-env ANTHROPIC_DEFAULT_HAIKU_MODEL \
  > "$log_path" 2>&1 < /dev/null &

pid=$!
printf '[%s] PID %s %s\n' "$(date -Is)" "$run_id" "$pid" | tee -a "$status_file"
printf 'started pid=%s run_id=%s variant=%s\n' "$pid" "$run_id" "$VARIANT"
printf 'log: %s\n' "$log_path"
