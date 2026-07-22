#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${B1_RUN_ID:?B1_RUN_ID is required}"
RELEASE_KIND="${B1_RELEASE_KIND:?B1_RELEASE_KIND is required}"
[[ "${RELEASE_KIND}" =~ ^(NORMAL|CONTROLLED_STOP)$ ]] || { echo "invalid B1 release kind" >&2; exit 2; }

set +u
source "${ROS_DISTRO_SETUP:-/opt/ros/humble/setup.bash}"
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/runs/b1_family_b/build/install/setup.bash}"
set -u

PX4_DIR="${PX4_B1_DIR:-${REPO_ROOT}/external/PX4-Autopilot-freshness-observability}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_BUILD="${B1_AGENT_BUILD:-${REPO_ROOT}/runs/freshness_agent_build}"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-${AGENT_BUILD}/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-${AGENT_BUILD}:${AGENT_BUILD}/temp_install/fastrtps-2.14/lib:${AGENT_BUILD}/temp_install/fastcdr-2.2.0/lib:${AGENT_BUILD}/temp_install/microxrcedds_client-2.4.3/lib}"
REFERENCE_BIN="${B1_REFERENCE_BIN:-${REPO_ROOT}/runs/b1_family_b/build/install/b1_reference_controller/lib/b1_reference_controller/b1_reference_controller}"
LOGGER_TOPICS_FILE="${B1_LOGGER_TOPICS_FILE:-${REPO_ROOT}/config/b1_reference_logger_topics.txt}"
RAW_DIR="${B1_RAW_ROOT:-${REPO_ROOT}/runs/motivation/b1_family_b/${RUN_ID}/raw}"
PROCESSED_DIR="${B1_PROCESSED_ROOT:-${RAW_DIR}/processed}"
CONTROL_DIR="${RAW_DIR}/control"

[[ -x "${PX4_BUILD}/bin/px4" ]] || { echo "B1 PX4 build is unavailable" >&2; exit 4; }
[[ -x "${AGENT_BIN}" ]] || { echo "locked DDS Agent is unavailable" >&2; exit 4; }
[[ -x "${REFERENCE_BIN}" ]] || { echo "B1 reference binary is unavailable" >&2; exit 4; }
[[ -f "${LOGGER_TOPICS_FILE}" ]] || { echo "B1 logger profile is unavailable" >&2; exit 4; }
[[ ! -e "${RAW_DIR}" ]] || { echo "refusing to overwrite B1 attempt" >&2; exit 3; }
if ss -H -lun "sport = :8888" 2>/dev/null | grep -q .; then
  echo "DDS port 8888 is occupied" >&2
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
REFERENCE_PID=""
MONITOR_PID=""
GZ_PID=""
GZ_PARTITION_NAME="uav_sf_b1_${RUN_ID//[^a-zA-Z0-9_]/_}"
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
  stop_process "${REFERENCE_PID}" INT
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then echo shutdown >&3; fi
  for _ in $(seq 1 100); do
    [[ -z "${PX4_PID}" ]] || ! kill -0 "${PX4_PID}" 2>/dev/null || { sleep 0.1; continue; }
    break
  done
  stop_process "${PX4_PID}" TERM
  stop_process "${GZ_PID}" TERM
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}" "${LOGGER_TOPICS_TARGET}"
}
trap finish_processes EXIT

LD_LIBRARY_PATH="${AGENT_LIBRARY_PATH}" "${AGENT_BIN}" udp4 -p 8888 >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!
(
  export GZ_SIM_RESOURCE_PATH=
  export GZ_SIM_SYSTEM_PLUGIN_PATH=
  export GZ_SIM_SERVER_CONFIG_PATH=
  set +u
  source "${PX4_BUILD}/rootfs/gz_env.sh"
  set -u
  exec env GZ_PARTITION="${GZ_PARTITION_NAME}" gz sim --seed 1 --verbose=1 -r -s "${PX4_DIR}/Tools/simulation/gz/worlds/default.sdf"
) >"${RAW_DIR}/gazebo.log" 2>&1 &
GZ_PID=$!
for _ in $(seq 1 100); do
  GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null | grep -q '/world/default/clock' && break
  kill -0 "${GZ_PID}" 2>/dev/null || { echo "Gazebo exited before readiness" >&2; exit 10; }
  sleep 0.1
done
GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null | grep -q '/world/default/clock' || { echo "Gazebo readiness timeout" >&2; exit 10; }

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
echo "param set MIS_TAKEOFF_ALT 1.5" >&3
echo "param set COM_DISARM_LAND 2" >&3
echo "param show COM_RC_IN_MODE" >&3
echo "param show NAV_RCL_ACT" >&3
echo "param show NAV_DLL_ACT" >&3
echo "param show COM_MODE_ARM_CHK" >&3
echo "param show MIS_TAKEOFF_ALT" >&3
echo "param show COM_DISARM_LAND" >&3
sleep 2

MONITOR_RESULT="${RAW_DIR}/monitor_result.json"
MONITOR_EVENTS="${RAW_DIR}/monitor_events.jsonl"
INTERRUPTION_RECORD="${RAW_DIR}/interruption_record.json"
INTERRUPTION_EVENTS="${RAW_DIR}/interruption_events.log"
READY_MARKER="${CONTROL_DIR}/release.ready"

python3 "${REPO_ROOT}/scripts/probes/b1_reference_flight_monitor.py" \
  --run-id "${RUN_ID}" --release-kind "${RELEASE_KIND}" \
  --output "${MONITOR_RESULT}" --events "${MONITOR_EVENTS}" \
  --control-dir "${CONTROL_DIR}" --ready-marker "${READY_MARKER}" \
  --interruption-record "${INTERRUPTION_RECORD}" >"${RAW_DIR}/monitor.log" 2>&1 &
MONITOR_PID=$!
"${REFERENCE_BIN}" >"${RAW_DIR}/reference_controller.log" 2>&1 &
REFERENCE_PID=$!

if [[ "${RELEASE_KIND}" == "CONTROLLED_STOP" ]]; then
  python3 "${REPO_ROOT}/scripts/probes/b1_controlled_stop.py" \
    --pid "${REFERENCE_PID}" --ready "${READY_MARKER}" \
    --output "${INTERRUPTION_RECORD}" --event-log "${INTERRUPTION_EVENTS}"
  wait "${REFERENCE_PID}" 2>/dev/null || true
  REFERENCE_PID=""
fi

while kill -0 "${MONITOR_PID}" 2>/dev/null; do
  kill -0 "${PX4_PID}" 2>/dev/null || { echo "PX4 exited during B1 attempt" >&2; exit 13; }
  kill -0 "${GZ_PID}" 2>/dev/null || { echo "Gazebo exited during B1 attempt" >&2; exit 13; }
  sleep 0.2
done
set +e
wait "${MONITOR_PID}"
MONITOR_STATUS=$?
set -e
MONITOR_PID=""
((MONITOR_STATUS == 0)) || { echo "B1 monitor rejected ${RUN_ID}" >&2; exit "${MONITOR_STATUS}"; }

stop_process "${REFERENCE_PID}" INT
REFERENCE_PID=""
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

LIFECYCLE_ARGS=(--lifecycle-log "${RAW_DIR}/reference_controller.log")
if [[ -f "${INTERRUPTION_EVENTS}" ]]; then LIFECYCLE_ARGS+=(--lifecycle-log "${INTERRUPTION_EVENTS}"); fi
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" \
  --ulog "${RAW_DIR}/flight.ulg" --output "${PROCESSED_DIR}/route_trace.jsonl" \
  --run-id "${RUN_ID}" --producer-events "${MONITOR_EVENTS}" "${LIFECYCLE_ARGS[@]}"
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${MONITOR_EVENTS}" --output "${PROCESSED_DIR}/clock_bridge.json"

REFERENCE_MODE="$(jq -r '.external_mode_id' "${MONITOR_RESULT}")"
CLASSIC_MODE="$(jq -r '.classic_mode_id' "${MONITOR_RESULT}")"
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --transition-source-mode "${CLASSIC_MODE}" --transition-target-mode "${REFERENCE_MODE}" \
  --source-artifact-complete --output "${PROCESSED_DIR}/installation_oracle.json"
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --transition-source-mode "${REFERENCE_MODE}" --transition-target-mode "${CLASSIC_MODE}" \
  --source-artifact-complete --output "${PROCESSED_DIR}/restoration_oracle.json"
SUMMARY_ARGS=(
  --run-id "${RUN_ID}" --monitor "${MONITOR_RESULT}"
  --trace "${PROCESSED_DIR}/route_trace.jsonl"
  --clock-bridge "${PROCESSED_DIR}/clock_bridge.json"
  --installation-oracle "${PROCESSED_DIR}/installation_oracle.json"
  --restoration-oracle "${PROCESSED_DIR}/restoration_oracle.json"
  --reference-log "${RAW_DIR}/reference_controller.log"
  --output "${PROCESSED_DIR}/b1_result.json"
)
if [[ -f "${INTERRUPTION_RECORD}" ]]; then SUMMARY_ARGS+=(--interruption-record "${INTERRUPTION_RECORD}"); fi
python3 "${REPO_ROOT}/scripts/analysis/summarize_b1_reference_run.py" "${SUMMARY_ARGS[@]}"
python3 "${REPO_ROOT}/scripts/tracing/compact_route_trace.py" \
  --input "${PROCESSED_DIR}/route_trace.jsonl" \
  --output "${PROCESSED_DIR}/route_trace.compact.jsonl" --stride 10 \
  --report "${PROCESSED_DIR}/trace_compaction.json"
mv "${PROCESSED_DIR}/route_trace.compact.jsonl" "${PROCESSED_DIR}/route_trace.jsonl"
echo "B1_REFERENCE_RUN=ACCEPTED run_id=${RUN_ID} release=${RELEASE_KIND}"
