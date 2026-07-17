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
MODE_BIN="${REPO_ROOT}/ros2_ws/install/route_transition_external_mode/lib/route_transition_external_mode/route_transition_external_mode"
RAW_DIR="${P0D1_RUN_ROOT:-${REPO_ROOT}/runs/p0d1}/${RUN_ID}/raw"
PROCESSED_DIR="${P0D1_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/p0d1}/${RUN_ID}"
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"
START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"
FIFO="${RAW_DIR}/px4.stdin"
rm -f "${FIFO}"
mkfifo "${FIFO}"
exec 3<>"${FIFO}"
PX4_PID="" AGENT_PID="" MODE_PID=""

stop_process() {
  local pid="${1:-}" signal="${2:-TERM}"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then return; fi
  kill -"${signal}" "${pid}" 2>/dev/null || true
  for _ in $(seq 1 100); do kill -0 "${pid}" 2>/dev/null || break; sleep 0.1; done
  wait "${pid}" 2>/dev/null || true
}
cleanup() {
  set +e
  stop_process "${MODE_PID}" INT
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
  HEADLESS=1 PX4_SIM_MODEL=gz_x500 "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!
for _ in $(seq 1 120); do
  grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null && break
  kill -0 "${PX4_PID}" 2>/dev/null || exit 10
  sleep 0.25
done
grep -q "pxh>" "${RAW_DIR}/px4.log"

wait_registered() {
  local log="$1" pid="$2"
  for _ in $(seq 1 200); do
    grep -q '"event_type":"external_mode_registered"' "${log}" 2>/dev/null && return 0
    kill -0 "${pid}" 2>/dev/null || return 1
    sleep 0.1
  done
  return 1
}

NORMAL_LOG="${RAW_DIR}/external_mode_normal.log"
"${MODE_BIN}" >"${NORMAL_LOG}" 2>&1 &
MODE_PID=$!
wait_registered "${NORMAL_LOG}" "${MODE_PID}"
sleep 2
kill -INT "${MODE_PID}"
normal_exit=false
for _ in $(seq 1 100); do kill -0 "${MODE_PID}" 2>/dev/null || { normal_exit=true; break; }; sleep 0.1; done
wait "${MODE_PID}" 2>/dev/null || true
MODE_PID=""
sleep 3

IMMEDIATE_LOG="${RAW_DIR}/external_mode_immediate.log"
"${MODE_BIN}" >"${IMMEDIATE_LOG}" 2>&1 &
MODE_PID=$!
wait_registered "${IMMEDIATE_LOG}" "${MODE_PID}"
sleep 2
# SIGTERM enters rclcpp's pre-shutdown callback, publishes unregister, and exits
# without an application-side acknowledgement wait: the immediate-exit case.
kill -TERM "${MODE_PID}"
immediate_exit=false
for _ in $(seq 1 100); do kill -0 "${MODE_PID}" 2>/dev/null || { immediate_exit=true; break; }; sleep 0.1; done
wait "${MODE_PID}" 2>/dev/null || true
MODE_PID=""
sleep 3

echo shutdown >&3
for _ in $(seq 1 200); do kill -0 "${PX4_PID}" 2>/dev/null || break; sleep 0.1; done
wait "${PX4_PID}" || true
PX4_PID=""
sleep 1
ULOG="$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
if [[ -z "${ULOG}" ]]; then echo "P0-D1 produced no ULog" >&2; exit 12; fi
cp "${ULOG}" "${RAW_DIR}/flight.ulg"
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" --ulog "${RAW_DIR}/flight.ulg" --output "${PROCESSED_DIR}/route_trace.jsonl" --run-id "${RUN_ID}" --lifecycle-log "${NORMAL_LOG}" --lifecycle-log "${IMMEDIATE_LOG}"
set +e
registration_args=(--trace "${PROCESSED_DIR}/route_trace.jsonl" --lifecycle-log "${NORMAL_LOG}" --lifecycle-log "${IMMEDIATE_LOG}" --output "${RAW_DIR}/runner_result.json")
if [[ "${normal_exit}" == "true" ]]; then registration_args+=(--normal-graceful-exit); fi
if [[ "${immediate_exit}" == "true" ]]; then registration_args+=(--immediate-exit); fi
python3 "${REPO_ROOT}/scripts/analysis/summarize_registration_lifecycle.py" "${registration_args[@]}"
RESULT_RC=$?
set -e
python3 "${REPO_ROOT}/scripts/analysis/summarize_route_trace.py" --trace "${PROCESSED_DIR}/route_trace.jsonl" --result "${RAW_DIR}/runner_result.json" --output "${PROCESSED_DIR}/route_summary.json" --scenario-label p0d1 --source "${RAW_DIR}/flight.ulg" --source "${NORMAL_LOG}" --source "${IMMEDIATE_LOG}" --observation-profile TRANSITION --uorb-queue-length 4
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" --trace "${PROCESSED_DIR}/route_trace.jsonl" --output "${PROCESSED_DIR}/route_oracle.json"
cp "${RAW_DIR}/runner_result.json" "${PROCESSED_DIR}/registration_lifecycle_result.json"
echo "P0D1_SCENARIO=$([[ "${RESULT_RC}" -eq 0 ]] && echo PASS || echo FAIL) run_id=${RUN_ID}"
exit "${RESULT_RC}"
