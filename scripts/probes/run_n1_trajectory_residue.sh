#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${N1_RUN_ID:?N1_RUN_ID is required}"
PHASE_BUCKET="${N1_HEALTH_PHASE_BUCKET:?N1_HEALTH_PHASE_BUCKET is required}"
SIMULATION_SEED="${N1_SIMULATION_SEED:?N1_SIMULATION_SEED is required}"
PROFILE="${N1_FRESHNESS_PROFILE:-${REPO_ROOT}/experiments/motivation/freshness/primary_preregistration.yaml}"
STABLE_SECONDS=5.0
TARGET_SECONDS=3.0
RECOVERY_SECONDS=2.0

[[ "${PHASE_BUCKET}" =~ ^(A|B|C)$ ]] || { echo "invalid N1 health phase bucket" >&2; exit 2; }
[[ "${SIMULATION_SEED}" =~ ^[0-9]+$ ]] || { echo "invalid N1 simulation seed" >&2; exit 2; }

set +u
source "${ROS_DISTRO_SETUP:-/opt/ros/humble/setup.bash}"
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/runs/freshness_harness_build/install/setup.bash}"
set -u

PX4_DIR="${PX4_FRESHNESS_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-control}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_BUILD="${FRESHNESS_AGENT_BUILD:-${REPO_ROOT}/runs/freshness_agent_build}"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-${AGENT_BUILD}/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-${AGENT_BUILD}:${AGENT_BUILD}/temp_install/fastrtps-2.14/lib:${AGENT_BUILD}/temp_install/fastcdr-2.2.0/lib:${AGENT_BUILD}/temp_install/microxrcedds_client-2.4.3/lib}"
PRODUCER_BIN="${FRESHNESS_PRODUCER_BIN:-${REPO_ROOT}/runs/freshness_harness_build/install/route_transition_external_mode/lib/route_transition_external_mode/external_mode_freshness_probe}"
LOGGER_TOPICS_FILE="${FRESHNESS_LOGGER_TOPICS_FILE:-${REPO_ROOT}/config/freshness_logger_topics.txt}"
RAW_DIR="${N1_RAW_ROOT:-${REPO_ROOT}/runs/motivation/n1_trajectory_residue/${RUN_ID}/raw}"
PROCESSED_DIR="${N1_PROCESSED_ROOT:-${RAW_DIR}/processed}"
CONTROL_DIR="${RAW_DIR}/channel_control"

[[ -x "${PX4_BUILD}/bin/px4" ]] || { echo "freshness PX4 build is unavailable" >&2; exit 4; }
[[ -x "${AGENT_BIN}" ]] || { echo "locked Micro-XRCE-DDS Agent is unavailable" >&2; exit 4; }
[[ -x "${PRODUCER_BIN}" ]] || { echo "freshness producer is unavailable" >&2; exit 4; }
[[ -f "${LOGGER_TOPICS_FILE}" ]] || { echo "freshness logger profile is unavailable" >&2; exit 4; }
[[ -f "${PROFILE}" ]] || { echo "freshness policy profile is unavailable" >&2; exit 4; }
[[ ! -e "${RAW_DIR}" ]] || { echo "refusing to overwrite existing raw attempt: ${RAW_DIR}" >&2; exit 3; }
if ss -H -lun "sport = :8888" 2>/dev/null | grep -q .; then
  echo "DDS campaign port 8888 is already occupied" >&2
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
PRODUCER_PID=""
MONITOR_PID=""
GZ_PID=""
GZ_PARTITION_NAME="uav_sf_n1_${RUN_ID//[^a-zA-Z0-9_]/_}"
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
  stop_process "${PRODUCER_PID}" INT
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

MONITOR_EVENTS="${RAW_DIR}/monitor_events.jsonl"
MONITOR_RESULT="${RAW_DIR}/monitor_result.json"
FAULT_RECORD="${RAW_DIR}/fault_record.json"
FAULT_EVENTS="${RAW_DIR}/fault_events.log"
READY_MARKER="${CONTROL_DIR}/experiment.ready"

python3 "${REPO_ROOT}/scripts/probes/freshness_flight_monitor.py" \
  --run-id "${RUN_ID}" --setpoint-type TRAJECTORY --fault-type TOTAL_PROCESS_STOP \
  --output "${MONITOR_RESULT}" --events "${MONITOR_EVENTS}" \
  --control-dir "${CONTROL_DIR}" --ready-marker "${READY_MARKER}" \
  --fault-record "${FAULT_RECORD}" --stable-seconds "${STABLE_SECONDS}" \
  --target-seconds "${TARGET_SECONDS}" --recovery-seconds "${RECOVERY_SECONDS}" \
  --minimum-clock-samples 20 --timeout 120 >"${RAW_DIR}/monitor.log" 2>&1 &
MONITOR_PID=$!

UAV_SF_SETPOINT_TYPE=TRAJECTORY \
UAV_SF_TRAJECTORY_VX_M_S=0.5 \
UAV_SF_THRUST_BODY_Z=-0.52 \
UAV_SF_CHANNEL_CONTROL_DIR="${CONTROL_DIR}" \
  "${PRODUCER_BIN}" >"${RAW_DIR}/external_mode.log" 2>&1 &
PRODUCER_PID=$!

python3 "${REPO_ROOT}/scripts/probes/inject_n1_trajectory_fault.py" \
  --pid "${PRODUCER_PID}" --phase-bucket "${PHASE_BUCKET}" --ready "${READY_MARKER}" \
  --health-log "${RAW_DIR}/external_mode.log" --output "${FAULT_RECORD}" \
  --event-log "${FAULT_EVENTS}"

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
stop_process "${PRODUCER_PID}" INT
PRODUCER_PID=""
((MONITOR_STATUS == 0)) || { echo "N1 monitor failed for ${RUN_ID}" >&2; exit "${MONITOR_STATUS}"; }

echo shutdown >&3
for _ in $(seq 1 200); do
  kill -0 "${PX4_PID}" 2>/dev/null || break
  sleep 0.1
done
kill -0 "${PX4_PID}" 2>/dev/null && { echo "PX4 normal shutdown timeout" >&2; exit 11; }
wait "${PX4_PID}" || true
PX4_PID=""
sleep 1

ULOG="$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "${ULOG}" && -f "${ULOG}" ]] || { echo "No ULog produced for ${RUN_ID}" >&2; exit 12; }
cp "${ULOG}" "${RAW_DIR}/flight.ulg"

python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" \
  --ulog "${RAW_DIR}/flight.ulg" --output "${PROCESSED_DIR}/route_trace.jsonl" --run-id "${RUN_ID}" \
  --producer-events "${MONITOR_EVENTS}" --lifecycle-log "${RAW_DIR}/external_mode.log" \
  --lifecycle-log "${FAULT_EVENTS}"
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${MONITOR_EVENTS}" --output "${PROCESSED_DIR}/clock_bridge.json"
python3 "${REPO_ROOT}/scripts/analysis/summarize_freshness_run.py" \
  --run-id "${RUN_ID}" --setpoint-type TRAJECTORY --fault-type TOTAL_PROCESS_STOP \
  --ulog "${RAW_DIR}/flight.ulg" --monitor-result "${MONITOR_RESULT}" \
  --monitor-events "${MONITOR_EVENTS}" --fault-record "${FAULT_RECORD}" \
  --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" \
  --output "${PROCESSED_DIR}/freshness_observation.json" --profile "${PROFILE}"
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" \
  --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --output "${PROCESSED_DIR}/route_oracle.json"
python3 "${REPO_ROOT}/scripts/oracles/pre_revocation_freshness_oracle.py" \
  --profile "${PROFILE}" --observation "${PROCESSED_DIR}/freshness_observation.json" \
  --output "${PROCESSED_DIR}/freshness_oracle.json"
cp "${MONITOR_RESULT}" "${PROCESSED_DIR}/scenario_monitor.json"
cp "${FAULT_RECORD}" "${PROCESSED_DIR}/fault_record.json"
python3 "${REPO_ROOT}/scripts/tracing/compact_route_trace.py" \
  --input "${PROCESSED_DIR}/route_trace.jsonl" \
  --output "${PROCESSED_DIR}/route_trace.compact.jsonl" --stride 10 \
  --report "${PROCESSED_DIR}/trace_compaction.json"
mv "${PROCESSED_DIR}/route_trace.compact.jsonl" "${PROCESSED_DIR}/route_trace.jsonl"

echo "N1_RUN=PASS run_id=${RUN_ID} phase_bucket=${PHASE_BUCKET}"
