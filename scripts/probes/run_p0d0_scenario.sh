#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${1:-}"
if [[ -z "${RUN_ID}" ]]; then echo "usage: $0 RUN_ID" >&2; exit 2; fi
set +u
source /opt/ros/jazzy/setup.bash
source "${REPO_ROOT}/ros2_ws/install/setup.bash"
set -u

PX4_DIR="${PX4_OBSERVABILITY_DIR:-${REPO_ROOT}/external/PX4-Autopilot-route-observability-q4-transition}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_PREFIX="${REPO_ROOT}/external/install/microxrce_agent"
RAW_DIR="${P0D0_RUN_ROOT:-${REPO_ROOT}/runs/p0d0}/${RUN_ID}/raw"
PROCESSED_DIR="${P0D0_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/p0d0}/${RUN_ID}"
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"
START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"
FIFO="${RAW_DIR}/px4.stdin"
rm -f "${FIFO}"
mkfifo "${FIFO}"
exec 3<>"${FIFO}"
PX4_PID="" AGENT_PID="" RUNNER_PID=""

stop_process() {
  local pid="${1:-}" signal="${2:-TERM}"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then return; fi
  kill -"${signal}" "${pid}" 2>/dev/null || true
  for _ in $(seq 1 50); do kill -0 "${pid}" 2>/dev/null || break; sleep 0.1; done
  if kill -0 "${pid}" 2>/dev/null; then kill -TERM "${pid}" 2>/dev/null || true; fi
  wait "${pid}" 2>/dev/null || true
}
cleanup() {
  set +e
  stop_process "${RUNNER_PID}" INT
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then echo shutdown >&3; fi
  stop_process "${PX4_PID}" TERM
  while read -r pid; do stop_process "${pid}" TERM; done < <(pgrep -P "$$" -f '^gz sim ' 2>/dev/null || true)
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}"
}
trap cleanup EXIT

LD_LIBRARY_PATH="${AGENT_PREFIX}/lib" "${AGENT_PREFIX}/bin/MicroXRCEAgent" udp4 -p 8888 >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!
(
  cd "${PX4_DIR}"
  PX4_PARAM_SDLOG_MODE=2 HEADLESS=1 PX4_SIM_MODEL=gz_x500 "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!
for _ in $(seq 1 120); do
  grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null && break
  kill -0 "${PX4_PID}" 2>/dev/null || exit 10
  sleep 0.25
done
grep -q "pxh>" "${RAW_DIR}/px4.log"
echo "param set COM_RC_IN_MODE 4" >&3
echo "param set NAV_RCL_ACT 0" >&3
echo "param set NAV_DLL_ACT 0" >&3
echo "param set COM_ARM_WO_GPS 1" >&3
echo "param set SDLOG_MODE 2" >&3
echo "param set RTL_RETURN_ALT 3" >&3
echo "param set RTL_DESCEND_ALT 2" >&3
sleep 2

RESULT_FILE="${RAW_DIR}/runner_result.json"
set +e
python3 "${REPO_ROOT}/scripts/probes/p0d0_internal_rearm.py" --output "${RESULT_FILE}" --timeout 240 >"${RAW_DIR}/runner.log" 2>&1
RUNNER_RC=$?
set -e
echo shutdown >&3
for _ in $(seq 1 200); do kill -0 "${PX4_PID}" 2>/dev/null || break; sleep 0.1; done
wait "${PX4_PID}" || true
PX4_PID=""
sleep 1

mapfile -t ULOGS < <(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-)
if [[ "${#ULOGS[@]}" -lt 1 ]]; then echo "P0-D0 produced no ULog" >&2; exit 12; fi
collector_args=() summary_sources=()
for index in "${!ULOGS[@]}"; do
  segment="${RAW_DIR}/flight_$(printf '%02d' "$((index + 1))").ulg"
  cp "${ULOGS[$index]}" "${segment}"
  collector_args+=(--ulog "${segment}")
  summary_sources+=(--source "${segment}")
done
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" "${collector_args[@]}" --output "${PROCESSED_DIR}/route_trace.jsonl" --run-id "${RUN_ID}" --producer-events "${RAW_DIR}/producer_events.jsonl"
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" --samples "${RAW_DIR}/producer_events.jsonl" --output "${PROCESSED_DIR}/clock_bridge.json" || true
python3 "${REPO_ROOT}/scripts/analysis/summarize_route_trace.py" --trace "${PROCESSED_DIR}/route_trace.jsonl" --result "${RESULT_FILE}" --output "${PROCESSED_DIR}/route_summary.json" --scenario-label p0d0 "${summary_sources[@]}" --source "${RAW_DIR}/producer_events.jsonl" --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" --observation-profile TRANSITION --uorb-queue-length 4
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" --trace "${PROCESSED_DIR}/route_trace.jsonl" --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" --output "${PROCESSED_DIR}/route_oracle.json"
echo "P0D0_SCENARIO=$([[ "${RUNNER_RC}" -eq 0 ]] && echo PASS || echo FAIL) run_id=${RUN_ID}"
exit "${RUNNER_RC}"
