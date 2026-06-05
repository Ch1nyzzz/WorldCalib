#!/usr/bin/env bash
# SWE-bench fail15 — single-proposer self-distill WMC (calib) arm.
# Thin wrapper: sets PROPOSER_VARIANT=calib and delegates to the shared launcher.
set -u -o pipefail
PROPOSER_VARIANT=calib exec "$(dirname "${BASH_SOURCE[0]}")/launch_swebench_fail15.sh" "$@"
