#!/usr/bin/env bash
# SWE-bench fail15 — pure-default no-WMC ablation (nowmc) arm.
# Thin wrapper: sets PROPOSER_VARIANT=nowmc and delegates to the shared launcher.
set -u -o pipefail
PROPOSER_VARIANT=nowmc exec "$(dirname "${BASH_SOURCE[0]}")/launch_swebench_fail15.sh" "$@"
