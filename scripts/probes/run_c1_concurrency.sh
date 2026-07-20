#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${C1_RUN_ID:?C1_RUN_ID is required}"
PAIR="${C1_EVENT_PAIR:?C1_EVENT_PAIR is required}"
ORDER="${C1_TIMING_ORDER:?C1_TIMING_ORDER is required}"
SIMULATION_SEED="${C1_SIMULATION_SEED:?C1_SIMULATION_SEED is required}"
[[ "${PAIR}" =~ ^(A|B|C|D|E)$ ]] || { echo "invalid C1 event pair" >&2; exit 2; }
[[ "${ORDER}" =~ ^(A_FIRST|NEAR_SIMULTANEOUS|B_FIRST)$ ]] || { echo "invalid C1 timing order" >&2; exit 2; }
[[ "${SIMULATION_SEED}" =~ ^[0-9]+$ ]] || { echo "invalid C1 simulation seed" >&2; exit 2; }

set +u
source "${ROS_DISTRO_SETUP:-/opt/ros/humble/setup.bash}"
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/runs/freshness_harness_build/install/setup.bash}"
source "${C1_WORKSPACE_SETUP:-${REPO_ROOT}/runs/c1_harness_build/install/setup.bash}"
set -u

PX4_DIR="${PX4_C1_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-control}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_BUILD="${C1_AGENT_BUILD:-${REPO_ROOT}/runs/freshness_agent_build}"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-${AGENT_BUILD}/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-${AGENT_BUILD}:${AGENT_BUILD}/temp_install/fastrtps-2.14/lib:${AGENT_BUILD}/temp_install/fastcdr-2.2.0/lib:${AGENT_BUILD}/temp_install/microxrcedds_client-2.4.3/lib}"
MODE_BIN="${C1_MODE_BIN:-${REPO_ROOT}/runs/c1_harness_build/install/route_transition_external_mode/lib/route_transition_external_mode/c1_concurrency_probe}"
LOGGER_TOPICS_FILE="${C1_LOGGER_TOPICS_FILE:-${REPO_ROOT}/config/freshness_logger_topics.txt}"
RAW_DIR="${C1_RAW_ROOT:-${REPO_ROOT}/runs/motivation/c1_concurrency/${RUN_ID}/raw}"
PROCESSED_DIR="${C1_PROCESSED_ROOT:-${RAW_DIR}/processed}"
CONTROL_DIR="${RAW_DIR}/channel_control"

[[ -x "${PX4_BUILD}/bin/px4" ]] || { echo "C1 PX4 build unavailable" >&2; exit 4; }
[[ -x "${AGENT_BIN}" ]] || { echo "C1 Micro-XRCE-DDS Agent unavailable" >&2; exit 4; }
[[ -x "${MODE_BIN}" ]] || { echo "C1 mode binary unavailable" >&2; exit 4; }
[[ -f "${LOGGER_TOPICS_FILE}" ]] || { echo "C1 logger profile unavailable" >&2; exit 4; }
[[ ! -e "${RAW_DIR}" ]] || { echo "refusing to overwrite C1 raw attempt" >&2; exit 3; }
if ss -H -lun "sport = :8888" 2>/dev/null | grep -q .; then
  echo "DDS campaign port 8888 is occupied" >&2
  exit 5
fi

mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}" "${CONTROL_DIR}"
LOGGER_TOPICS_TARGET="${PX4_BUILD}/rootfs/0/etc/logging/logger_topics.txt"
install -D -m 0644 "${LOGGER_TOPICS_FILE}" "${LOGGER_TOPICS_TARGET}"
START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"
rm -f "${PX4_BUILD}/rootfs/0/parameters.bson" "${PX4_BUILD}/rootfs/0/parameters_backup.bson"

PX4_PID=""
AGENT_PID=""
MODE_PID=""
MONITOR_PID=""
GZ_PID=""
GZ_PARTITION_NAME="uav_sf_c1_${RUN_ID//[^a-zA-Z0-9_]/_}"
FIFO="${RAW_DIR}/px4.stdin"
mkfifo "${FIFO}"
exec 3<>"${FIFO}"

stop_process() {
  local pid="${1:-}"
  local selected_signal="${2:-TERM}"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then return; fi
  kill -"${selected_signal}" "${pid}" 2>/dev/null || true
  for _ in $(seq 1 50); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${pid}" 2>/dev/null; then kill -KILL "${pid}" 2>/dev/null || true; fi
  wait "${pid}" 2>/dev/null || true
}

finish_processes() {
  set +e
  stop_process "${MONITOR_PID}" INT
  stop_process "${MODE_PID}" TERM
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then
    echo shutdown >&3
    for _ in $(seq 1 100); do
      kill -0 "${PX4_PID}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  while read -r child_pid; do stop_process "${child_pid}" TERM; done \
    < <(pgrep -P "$$" -f '^gz sim ' 2>/dev/null || true)
  stop_process "${GZ_PID}" TERM
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}" "${LOGGER_TOPICS_TARGET}"
}
trap finish_processes EXIT

LD_LIBRARY_PATH="${AGENT_LIBRARY_PATH}" \
  "${AGENT_BIN}" udp4 -p 8888 >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!
(
  export GZ_SIM_RESOURCE_PATH=
  export GZ_SIM_SYSTEM_PLUGIN_PATH=
  export GZ_SIM_SERVER_CONFIG_PATH=
  set +u
  source "${PX4_BUILD}/rootfs/gz_env.sh"
  set -u
  exec env GZ_PARTITION="${GZ_PARTITION_NAME}" gz sim --seed "${SIMULATION_SEED}" \
    --verbose=1 -r -s "${PX4_DIR}/Tools/simulation/gz/worlds/default.sdf"
) >"${RAW_DIR}/gazebo.log" 2>&1 &
GZ_PID=$!
for _ in $(seq 1 100); do
  GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null | grep -q '/world/default/clock' && break
  kill -0 "${GZ_PID}" 2>/dev/null || { echo "Gazebo exited before readiness" >&2; exit 10; }
  sleep 0.1
done
GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null \
  | grep -q '/world/default/clock' || { echo "Gazebo readiness timeout" >&2; exit 10; }

(
  cd "${PX4_DIR}"
  GZ_PARTITION="${GZ_PARTITION_NAME}" PX4_GZ_STANDALONE=1 GZ_SIM_RESOURCE_PATH= \
    PX4_PARAM_SDLOG_MODE=0 PX4_PARAM_SDLOG_PROFILE=0 HEADLESS=1 PX4_SIM_MODEL=gz_x500 \
    "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!
for _ in $(seq 1 120); do
  grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null && break
  kill -0 "${PX4_PID}" 2>/dev/null || { echo "PX4 exited before readiness" >&2; exit 10; }
  sleep 0.25
done
grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null || { echo "PX4 readiness timeout" >&2; exit 10; }

echo "param set COM_RC_IN_MODE 4" >&3
echo "param set NAV_RCL_ACT 0" >&3
echo "param set NAV_DLL_ACT 0" >&3
echo "param set COM_ARM_WO_GPS 1" >&3
echo "param set COM_MODE_ARM_CHK 1" >&3
sleep 2

MODE_PID_FILE="${RAW_DIR}/mode.pid"
python3 "${REPO_ROOT}/scripts/probes/c1_concurrency_monitor.py" \
  --run-id "${RUN_ID}" --pair "${PAIR}" --order "${ORDER}" \
  --output "${RAW_DIR}/monitor_result.json" --events "${RAW_DIR}/monitor_events.jsonl" \
  --control-dir "${CONTROL_DIR}" --mode-pid-file "${MODE_PID_FILE}" --timeout 120 \
  >"${RAW_DIR}/monitor.log" 2>&1 &
MONITOR_PID=$!
sleep 1
UAV_SF_CHANNEL_CONTROL_DIR="${CONTROL_DIR}" \
  "${MODE_BIN}" >"${RAW_DIR}/external_mode.log" 2>&1 &
MODE_PID=$!
printf '%s\n' "${MODE_PID}" >"${MODE_PID_FILE}"

while kill -0 "${MONITOR_PID}" 2>/dev/null; do
  monitor_state="$(ps -o stat= -p "${MONITOR_PID}" 2>/dev/null | tr -d ' ' || true)"
  [[ "${monitor_state}" == Z* ]] && break
  kill -0 "${PX4_PID}" 2>/dev/null || { echo "PX4 exited during ${RUN_ID}" >&2; exit 13; }
  kill -0 "${GZ_PID}" 2>/dev/null || { echo "Gazebo exited during ${RUN_ID}" >&2; exit 13; }
  sleep 0.2
done
set +e
wait "${MONITOR_PID}"
MONITOR_STATUS=$?
set -e
MONITOR_PID=""
stop_process "${MODE_PID}" TERM
MODE_PID=""
((MONITOR_STATUS == 0)) || { echo "C1 monitor failed for ${RUN_ID}" >&2; exit "${MONITOR_STATUS}"; }

echo shutdown >&3
for _ in $(seq 1 200); do
  kill -0 "${PX4_PID}" 2>/dev/null || break
  sleep 0.1
done
kill -0 "${PX4_PID}" 2>/dev/null && { echo "PX4 shutdown timeout" >&2; exit 11; }
wait "${PX4_PID}" || true
PX4_PID=""
sleep 1

ULOG="$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "${ULOG}" && -f "${ULOG}" ]] || { echo "No ULog produced for ${RUN_ID}" >&2; exit 12; }
cp "${ULOG}" "${RAW_DIR}/flight.ulg"
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" \
  --ulog "${RAW_DIR}/flight.ulg" --output "${PROCESSED_DIR}/route_trace.jsonl" --run-id "${RUN_ID}" \
  --producer-events "${RAW_DIR}/monitor_events.jsonl" --lifecycle-log "${RAW_DIR}/external_mode.log"
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${RAW_DIR}/monitor_events.jsonl" --output "${PROCESSED_DIR}/clock_bridge.json"
python3 "${REPO_ROOT}/scripts/oracles/authority_event_linearization_oracle.py" \
  --runner-result "${RAW_DIR}/monitor_result.json" --events "${RAW_DIR}/monitor_events.jsonl" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --output "${PROCESSED_DIR}/authority_linearization_oracle.json"
python3 "${REPO_ROOT}/scripts/tracing/compact_route_trace.py" \
  --input "${PROCESSED_DIR}/route_trace.jsonl" \
  --output "${PROCESSED_DIR}/route_trace.compact.jsonl" --stride 10 \
  --report "${PROCESSED_DIR}/trace_compaction.json"
mv "${PROCESSED_DIR}/route_trace.compact.jsonl" "${PROCESSED_DIR}/route_trace.jsonl"

echo "C1_RUN=PASS run_id=${RUN_ID} pair=${PAIR} timing_order=${ORDER}"
