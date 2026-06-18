#!/usr/bin/env bash
# One-shot watcher: wait for the calib arm's iter-0 seed (run_summary.json) to be
# written, then launch the nowmc arm reusing that exact seed via BASELINE_DIR so
# both arms share one baseline. Self-launched with setsid; logs to its own file.
set -u
cd /data/home/yuhan/WorldCalib

TS="20260618_091359"
CALIB_RID="autolab_claudekimi_k27_calib_iter10_${TS}"
SEED="runs/${CALIB_RID}/run_summary.json"
WLOG="logs/autolab_nowmc_watcher_${TS}.log"

echo "[$(date -Is)] watcher start; waiting for ${SEED}" >> "$WLOG"

# Poll up to ~3h (1080 * 10s) for the seed summary.
for _ in $(seq 1 1080); do
  if [ -f "$SEED" ]; then break; fi
  # bail out early if the calib optimizer died without producing a seed
  if ! pgrep -f "$CALIB_RID" >/dev/null 2>&1; then
    if [ ! -f "$SEED" ]; then
      echo "[$(date -Is)] FATAL: calib proc gone and no seed written; aborting nowmc" >> "$WLOG"
      exit 1
    fi
  fi
  sleep 10
done

if [ ! -f "$SEED" ]; then
  echo "[$(date -Is)] TIMEOUT: seed never appeared; not launching nowmc" >> "$WLOG"
  exit 1
fi

echo "[$(date -Is)] seed ready; launching nowmc with BASELINE_DIR=runs/${CALIB_RID}" >> "$WLOG"

AUTOLAB_TASK_IDS="aes128_ctr,bm25_search_go,bvh_raytracer,fft_rust,fredkin_sort_network,gaussian_blur,hash_join,levenshtein_distance,radix_sort,sstable_compaction_rs" \
AUTOLAB_SKIP_PATCH_CHECK=1 AUTOLAB_N_ATTEMPTS=3 AUTOLAB_SCORE_MODE=best \
AUTOLAB_HARBOR_MODEL=openai/deepseek-v4-flash \
EVAL_WORKERS=10 AUTOLAB_CONCURRENCY=3 \
PROPOSER_BACKEND=kimi-docker ITERATIONS=10 TS="$TS" \
BASELINE_DIR="runs/${CALIB_RID}" \
PROPOSER_VARIANT=nowmc \
bash scripts/launch_autolab_calib.sh >> "$WLOG" 2>&1

echo "[$(date -Is)] nowmc launch invoked (rc=$?)" >> "$WLOG"
