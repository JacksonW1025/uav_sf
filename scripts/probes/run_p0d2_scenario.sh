#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then echo "usage: $0 RUN_ID" >&2; exit 2; fi

export PX4_OBSERVABILITY_DIR="${PX4_OBSERVABILITY_DIR:-${REPO_ROOT}/external/PX4-Autopilot-route-observability-q4-transition}"
export P0D_RUN_ROOT="${P0D2_RUN_ROOT:-${REPO_ROOT}/runs/p0d2/${RUN_ID}/raw}"
export P0D_PROCESSED_ROOT="${P0D2_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/p0d2/${RUN_ID}}"
export P0D_RUNNER="${REPO_ROOT}/scripts/probes/p0d2_full_reentry.py"
export P0D_POST_ANALYZER="${REPO_ROOT}/scripts/analysis/summarize_p0d2_result.py"
export P0D_SCENARIO_LABEL="p0d2"
export P0D_UORB_QUEUE_LENGTH=4
export P0D_LOGGER_TOPICS_FILE="${REPO_ROOT}/config/phase_a2_minimal_logger_topics.txt"
export P0D_SDLOG_PROFILE=0
exec "${REPO_ROOT}/scripts/probes/run_p0d_scenario.sh" "${RUN_ID}"
