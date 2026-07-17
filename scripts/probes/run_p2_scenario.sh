#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OBJECT="${1:-}"
FAULT_CLASS="${2:-}"
RUN_ID="${3:-}"
if [[ ! "${OBJECT}" =~ ^(offboard|external)$ ]] \
  || [[ ! "${FAULT_CLASS}" =~ ^(sigterm|sigkill|sigstop_sigcont)$ ]] \
  || [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 {offboard|external} {sigterm|sigkill|sigstop_sigcont} RUN_ID" >&2
  exit 2
fi
export ROUTE_EXPERIMENT_KIND=p2
export ROUTE_EXPERIMENT_OBJECT="${OBJECT}"
export ROUTE_EXPERIMENT_FAULT_CLASS="${FAULT_CLASS}"
export ROUTE_EXPERIMENT_RUN_ID="${RUN_ID}"
export ROUTE_EXPERIMENT_HEARTBEAT_OR_HEALTH=on
export ROUTE_EXPERIMENT_SETPOINT=on
exec "${REPO_ROOT}/scripts/probes/run_route_experiment.sh"
