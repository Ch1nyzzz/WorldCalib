#!/usr/bin/env bash
# WorldCalib launcher: SWE-bench coding agent, 15 hard failed-issue train set,
# WMC-vs-noWMC ablation. Parametrized by PROPOSER_VARIANT (calib | nowmc).
#
#   proposer : kimi-k2.6 via claude-code in docker-claude-kimi:latest
#   solver   : deepseek-v4-flash (mini-SWE-agent), via the eval-gate script
#   data     : data/swebench_train_fail15.json  (15 of the 19 seed-failed issues)
#   baseline : runs/baseline_swebench_fail15     (iter0 = 0/15, reused not rerun)
#   variant  : calib -> swebench_calib skill (single-proposer self-distill WMC)
#              nowmc -> swebench_nowmc skill (pure-default ablation)
#   NO fan-out, NO best-of-N, NO external critic.
#
# Usually invoked through the thin wrappers launch_swebench_fail15_calib.sh /
# _nowmc.sh, which set PROPOSER_VARIANT for you.
set -u -o pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROPOSER_VARIANT="${PROPOSER_VARIANT:?set PROPOSER_VARIANT=calib|nowmc (or use the _calib/_nowmc wrapper)}"
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

for v in KIMI_API_KEY DEEPSEEK_API_KEY OPENAI_API_KEY; do
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

# Embeddings: OpenAI official text-embedding-3-small (trace_similar backend).
unset DIFF_EMBEDDING_MODEL
unset OPENAI_BASE_URL

export ENABLE_TOOL_SEARCH=false
export ANTHROPIC_DEFAULT_OPUS_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="${KIMI_MODEL}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${KIMI_MODEL}"
export CLAUDE_CODE_SUBAGENT_MODEL="${KIMI_MODEL}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
ITERATIONS="${ITERATIONS:-5}"
EVAL_WORKERS="${EVAL_WORKERS:-8}"
EVAL_TIMEOUT_S="${EVAL_TIMEOUT_S:-900}"
# Proposer hard budget: 1.5h. kimi max-effort needs the room; on overrun the
# runner docker-kills the orphaned container.
PROPOSE_TIMEOUT_S="${PROPOSE_TIMEOUT_S:-5400}"
DOCKER_USER_SPEC="${DOCKER_USER_SPEC:-$(id -u):$(id -g)}"

DATA_PATH="${DATA_PATH:-data/swebench_train_fail15.json}"
BASELINE_DIR="${BASELINE_DIR:-runs/baseline_swebench_fail15}"

# Solver: deepseek-v4-flash mini-SWE-agent, run + eval through this repo's gate.
# NB: the command templates contain literal {source_path}/{task_dir} placeholders
# (substituted later by the optimizer). They must NOT be wrapped in a
# ${VAR:-default} expansion — the '}' of {source_path} would prematurely close
# the parameter expansion and corrupt the command. Use plain guarded assignments.
RUN_SCRIPT="$(pwd)/scripts/run_miniswe_swebench_single.py"
if [ -z "${MINISWE_RUN_CMD:-}" ]; then
  MINISWE_RUN_CMD="python ${RUN_SCRIPT} run --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir} --model openai/deepseek-v4-flash --base-url https://api.deepseek.com/v1 --max-tokens 4096 --api-key-env DEEPSEEK_API_KEY"
fi
if [ -z "${MINISWE_EVAL_CMD:-}" ]; then
  MINISWE_EVAL_CMD="python ${RUN_SCRIPT} eval --source-path {source_path} --instance-path {instance_path} --patch-path {patch_path} --task-dir {task_dir}"
fi

if [ ! -f "${BASELINE_DIR}/run_summary.json" ]; then
  printf 'fatal: baseline missing %s/run_summary.json (run scripts/build_swebench_fail15.py)\n' "$BASELINE_DIR" >&2
  exit 1
fi
if [ ! -f "$DATA_PATH" ]; then
  printf 'fatal: data missing %s (run scripts/build_swebench_fail15.py)\n' "$DATA_PATH" >&2
  exit 1
fi

mkdir -p logs runs
status_file="logs/launch_swebench_fail15_${PROPOSER_VARIANT}_${TS}.status"
: > "$status_file"
printf '[%s] LAUNCHER start ts=%s iter=%s variant=%s proposer=claudekimi(%s) solver=deepseek-v4-flash data=%s\n' \
  "$(date -Is)" "$TS" "$ITERATIONS" "$PROPOSER_VARIANT" "$KIMI_MODEL" "$DATA_PATH" >> "$status_file"

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

run_id="swebench_fail15_claudekimi_k26_dsflash_${PROPOSER_VARIANT}_iter${ITERATIONS}_${TS}"
log_path="logs/${run_id}.log"

printf '[%s] START %s baseline=%s\n[%s] LOG   %s\n' \
  "$(date -Is)" "$run_id" "$BASELINE_DIR" "$(date -Is)" "$log_path" >> "$status_file"

setsid worldcalib-optimize \
  --swebench \
  --split train --limit 15 \
  --swebench-data-path "$DATA_PATH" \
  --mini-swe-agent-source-path references/vendor/mini-swe-agent \
  --mini-swe-agent-command "$MINISWE_RUN_CMD" \
  --mini-swe-agent-eval-command "$MINISWE_EVAL_CMD" \
  --proposer-variant "$PROPOSER_VARIANT" \
  --baseline-dir "$BASELINE_DIR" \
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
