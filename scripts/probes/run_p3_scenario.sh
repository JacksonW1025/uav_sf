#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OBJECT="${1:-}"
HEARTBEAT_OR_HEALTH="${2:-}"
SETPOINT="${3:-}"
RUN_ID="${4:-}"
if [[ ! "${OBJECT}" =~ ^(offboard|external)$ ]] \
  || [[ ! "${HEARTBEAT_OR_HEALTH}" =~ ^(on|off)$ ]] \
  || [[ ! "${SETPOINT}" =~ ^(on|off)$ ]] \
  || [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 {offboard|external} {on|off} {on|off} RUN_ID" >&2
  exit 2
fi
export ROUTE_EXPERIMENT_KIND=p3
export ROUTE_EXPERIMENT_OBJECT="${OBJECT}"
export ROUTE_EXPERIMENT_RUN_ID="${RUN_ID}"
export ROUTE_EXPERIMENT_HEARTBEAT_OR_HEALTH="${HEARTBEAT_OR_HEALTH}"
export ROUTE_EXPERIMENT_SETPOINT="${SETPOINT}"
exec "${REPO_ROOT}/scripts/probes/run_route_experiment.sh"
