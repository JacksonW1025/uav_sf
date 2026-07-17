#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXPERIMENT_KIND="${ROUTE_EXPERIMENT_KIND:?ROUTE_EXPERIMENT_KIND is required}"
OBJECT="${ROUTE_EXPERIMENT_OBJECT:?ROUTE_EXPERIMENT_OBJECT is required}"
RUN_ID="${ROUTE_EXPERIMENT_RUN_ID:?ROUTE_EXPERIMENT_RUN_ID is required}"
FAULT_CLASS="${ROUTE_EXPERIMENT_FAULT_CLASS:-}"
HEARTBEAT_OR_HEALTH="${ROUTE_EXPERIMENT_HEARTBEAT_OR_HEALTH:-on}"
SETPOINT="${ROUTE_EXPERIMENT_SETPOINT:-on}"
FAULT_OFFSET_S="${ROUTE_EXPERIMENT_FAULT_OFFSET_S:-0.0}"
MIN_CLOCK_SAMPLES="${ROUTE_EXPERIMENT_MIN_CLOCK_SAMPLES:-0}"
BEHAVIOR_CONTEXT="${ROUTE_EXPERIMENT_BEHAVIOR_CONTEXT:-hover}"
POST_OBSERVATION_CAPTURE_S="${ROUTE_EXPERIMENT_POST_OBSERVATION_CAPTURE_S:-0.75}"
LOGGER_PROFILE="${ROUTE_EXPERIMENT_SDLOG_PROFILE:-1}"
LOGGER_TOPICS_FILE="${ROUTE_EXPERIMENT_LOGGER_TOPICS_FILE:-}"
SIMULATION_SEED="${ROUTE_EXPERIMENT_SIMULATION_SEED:-1}"

set +u
source "${ROS_DISTRO_SETUP:-/opt/ros/jazzy/setup.bash}"
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/ros2_ws/install/setup.bash}"
set -u

PX4_DIR="${PX4_OBSERVABILITY_DIR:-${REPO_ROOT}/external/PX4-Autopilot-route-observability-q4-transition}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_PREFIX="${REPO_ROOT}/external/install/microxrce_agent"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-${AGENT_PREFIX}/bin/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-${AGENT_PREFIX}/lib}"
EXTERNAL_MODE_BIN="${ROUTE_EXTERNAL_MODE_BIN:-${REPO_ROOT}/ros2_ws/install/route_transition_external_mode/lib/route_transition_external_mode/route_transition_external_mode}"
RAW_DIR="${ROUTE_EXPERIMENT_RAW_ROOT:-${REPO_ROOT}/runs/${EXPERIMENT_KIND}/${RUN_ID}/raw}"
PROCESSED_DIR="${ROUTE_EXPERIMENT_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/${EXPERIMENT_KIND}/${RUN_ID}}"
CONTROL_DIR="${RAW_DIR}/channel_control"
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}" "${CONTROL_DIR}"
rm -f \
  "${CONTROL_DIR}/activate" \
  "${CONTROL_DIR}/context.active" \
  "${CONTROL_DIR}/experiment.ready" \
  "${CONTROL_DIR}/health_reply.off" \
  "${CONTROL_DIR}/heartbeat.off" \
  "${CONTROL_DIR}/setpoint.off" \
  "${CONTROL_DIR}/stop"
LOGGER_TOPICS_TARGET="${PX4_BUILD}/rootfs/0/etc/logging/logger_topics.txt"
if [[ -n "${LOGGER_TOPICS_FILE}" ]]; then
  install -D -m 0644 "${LOGGER_TOPICS_FILE}" "${LOGGER_TOPICS_TARGET}"
fi
START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"
rm -f "${PX4_BUILD}/rootfs/0/parameters.bson" \
  "${PX4_BUILD}/rootfs/0/parameters_backup.bson"

PX4_PID=""
AGENT_PID=""
PRODUCER_PID=""
MONITOR_PID=""
STOP_WATCHER_PID=""
GZ_PID=""
GZ_PARTITION_NAME="uav_sf_${RUN_ID//[^a-zA-Z0-9_]/_}"
FIFO="${RAW_DIR}/px4.stdin"
rm -f "${FIFO}"
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
  touch "${CONTROL_DIR}/stop"
  stop_process "${MONITOR_PID}" INT
  stop_process "${STOP_WATCHER_PID}" TERM
  stop_process "${PRODUCER_PID}" INT
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then
    echo shutdown >&3
    for _ in $(seq 1 100); do
      kill -0 "${PX4_PID}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  while read -r gz_pid; do stop_process "${gz_pid}" TERM; done \
    < <(pgrep -P "$$" -f '^gz sim ' 2>/dev/null || true)
  stop_process "${GZ_PID}" TERM
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}"
  if [[ -n "${LOGGER_TOPICS_FILE}" ]]; then rm -f "${LOGGER_TOPICS_TARGET}"; fi
}
trap finish_processes EXIT

LD_LIBRARY_PATH="${AGENT_LIBRARY_PATH}" \
  "${AGENT_BIN}" udp4 -p 8888 \
  >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
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
    PX4_PARAM_SDLOG_MODE=0 PX4_PARAM_SDLOG_PROFILE="${LOGGER_PROFILE}" \
    HEADLESS=1 PX4_SIM_MODEL=gz_x500 \
    "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!

for _ in $(seq 1 120); do
  if grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null; then break; fi
  if ! kill -0 "${PX4_PID}" 2>/dev/null; then
    echo "PX4 exited before shell readiness" >&2
    exit 10
  fi
  sleep 0.25
done
if ! grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null; then
  echo "PX4 shell did not become ready within 30 seconds" >&2
  exit 10
fi

echo "param set COM_RC_IN_MODE 4" >&3
echo "param set NAV_RCL_ACT 0" >&3
echo "param set NAV_DLL_ACT 0" >&3
echo "param set COM_ARM_WO_GPS 1" >&3
echo "param set COM_OF_LOSS_T 1.0" >&3
echo "param set COM_OBL_RC_ACT 5" >&3
sleep 2

PRODUCER_EVENTS="${RAW_DIR}/producer_events.jsonl"
MONITOR_EVENTS="${RAW_DIR}/monitor_events.jsonl"
MONITOR_RESULT="${RAW_DIR}/monitor_result.json"
FAULT_RECORD="${RAW_DIR}/fault_record.json"
FAULT_EVENTS="${RAW_DIR}/fault_events.log"
READY_MARKER="${CONTROL_DIR}/experiment.ready"

monitor_args=(
  --experiment-kind "${EXPERIMENT_KIND}"
  --object "${OBJECT}"
  --output "${MONITOR_RESULT}"
  --events "${MONITOR_EVENTS}"
  --control-dir "${CONTROL_DIR}"
  --ready-marker "${READY_MARKER}"
  --heartbeat-or-health "${HEARTBEAT_OR_HEALTH}"
  --setpoint "${SETPOINT}"
  --minimum-clock-samples "${MIN_CLOCK_SAMPLES}"
  --timeout 150
)
if [[ "${EXPERIMENT_KIND}" == "p2" ]]; then
  monitor_args+=(--fault-record "${FAULT_RECORD}" --fault-class "${FAULT_CLASS}")
fi

start_monitor() {
  python3 "${REPO_ROOT}/scripts/probes/route_fault_monitor.py" "${monitor_args[@]}" \
    >"${RAW_DIR}/monitor.log" 2>&1 &
  MONITOR_PID=$!
}

if [[ "${OBJECT}" == "offboard" ]]; then
  UAV_SF_BEHAVIOR_CONTEXT="${BEHAVIOR_CONTEXT}" \
    python3 "${REPO_ROOT}/scripts/probes/offboard_channel_producer.py" \
    --events "${PRODUCER_EVENTS}" --control-dir "${CONTROL_DIR}" --timeout 150 \
    >"${RAW_DIR}/producer.log" 2>&1 &
  PRODUCER_PID=$!
  start_monitor
else
  start_monitor
  sleep 0.5
  UAV_SF_BEHAVIOR_CONTEXT="${BEHAVIOR_CONTEXT}" UAV_SF_LOG_EVERY_SETPOINT=1 \
    UAV_SF_CHANNEL_CONTROL_DIR="${CONTROL_DIR}" \
    "${EXTERNAL_MODE_BIN}" \
    >"${RAW_DIR}/external_mode.log" 2>&1 &
  PRODUCER_PID=$!
  (
    while [[ ! -f "${CONTROL_DIR}/stop" ]]; do sleep 0.1; done
    sleep 1.0
    kill -INT "${PRODUCER_PID}" 2>/dev/null || true
  ) &
  STOP_WATCHER_PID=$!
fi

if [[ "${EXPERIMENT_KIND}" == "p2" ]]; then
  python3 "${REPO_ROOT}/scripts/probes/inject_process_fault.py" \
    --pid "${PRODUCER_PID}" --fault "${FAULT_CLASS}" --ready "${READY_MARKER}" \
    --delay-seconds "${FAULT_OFFSET_S}" \
    --output "${FAULT_RECORD}" --event-log "${FAULT_EVENTS}"
fi

while kill -0 "${MONITOR_PID}" 2>/dev/null; do
  monitor_state="$(ps -o stat= -p "${MONITOR_PID}" 2>/dev/null | tr -d ' ' || true)"
  if [[ "${monitor_state}" == Z* ]]; then break; fi
  if ! kill -0 "${PX4_PID}" 2>/dev/null; then
    echo "PX4 exited during route experiment ${RUN_ID}" >&2
    stop_process "${MONITOR_PID}" INT
    MONITOR_PID=""
    exit 13
  fi
  sleep 0.2
done
set +e
wait "${MONITOR_PID}"
MONITOR_STATUS=$?
set -e
MONITOR_PID=""
if [[ "${EXPERIMENT_KIND}" == "p3" ]] && ((MONITOR_STATUS == 0)); then
  # The monitor closes physical measurement before requesting Hold.  Preserve a
  # full post-transition writer window before process and PX4 teardown so the
  # fixed +/-500 ms route-oracle window is evidence-complete.
  sleep "${POST_OBSERVATION_CAPTURE_S}"
fi
touch "${CONTROL_DIR}/stop"
stop_process "${PRODUCER_PID}" INT
PRODUCER_PID=""
stop_process "${STOP_WATCHER_PID}" TERM
STOP_WATCHER_PID=""
if ((MONITOR_STATUS != 0)); then
  echo "route monitor failed for ${RUN_ID}" >&2
  exit "${MONITOR_STATUS}"
fi

echo shutdown >&3
for _ in $(seq 1 200); do
  kill -0 "${PX4_PID}" 2>/dev/null || break
  sleep 0.1
done
if kill -0 "${PX4_PID}" 2>/dev/null; then
  echo "PX4 did not exit after normal shutdown" >&2
  exit 11
fi
wait "${PX4_PID}" || true
PX4_PID=""
sleep 1

ULOG="$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
if [[ -z "${ULOG}" || ! -f "${ULOG}" ]]; then
  echo "No ULog was produced for ${RUN_ID}" >&2
  exit 12
fi
cp "${ULOG}" "${RAW_DIR}/flight.ulg"

if [[ "${OBJECT}" == "offboard" ]]; then
  TRACE_PRODUCER="${PRODUCER_EVENTS}"
else
  TRACE_PRODUCER="${MONITOR_EVENTS}"
fi
CLOCK_SAMPLES="${MONITOR_EVENTS}"
collector_args=(
  --ulog "${RAW_DIR}/flight.ulg"
  --output "${PROCESSED_DIR}/route_trace.jsonl"
  --run-id "${RUN_ID}"
  --producer-events "${TRACE_PRODUCER}"
)
if [[ -f "${RAW_DIR}/external_mode.log" ]]; then
  collector_args+=(--lifecycle-log "${RAW_DIR}/external_mode.log")
fi
if [[ -f "${FAULT_EVENTS}" ]]; then
  collector_args+=(--lifecycle-log "${FAULT_EVENTS}")
fi
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" "${collector_args[@]}"
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${CLOCK_SAMPLES}" --output "${PROCESSED_DIR}/clock_bridge.json"
summary_args=(
  --trace "${PROCESSED_DIR}/route_trace.jsonl"
  --result "${MONITOR_RESULT}"
  --output "${PROCESSED_DIR}/route_summary.json"
  --scenario-label "${EXPERIMENT_KIND}_${OBJECT}"
  --source "${RAW_DIR}/flight.ulg"
  --source "${TRACE_PRODUCER}"
  --source "${CLOCK_SAMPLES}"
  --clock-bridge "${PROCESSED_DIR}/clock_bridge.json"
  --observation-profile TRANSITION
  --uorb-queue-length 4
  --build-provenance "${REPO_ROOT}/data/processed/phase_a2/queue_q4_build_provenance.json"
)
if [[ -f "${RAW_DIR}/external_mode.log" ]]; then
  summary_args+=(--source "${RAW_DIR}/external_mode.log")
fi
if [[ -f "${FAULT_RECORD}" ]]; then summary_args+=(--source "${FAULT_RECORD}"); fi
python3 "${REPO_ROOT}/scripts/analysis/summarize_route_trace.py" "${summary_args[@]}"
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" \
  --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --output "${PROCESSED_DIR}/route_oracle.json"
python3 "${REPO_ROOT}/scripts/analysis/summarize_route_experiment.py" \
  --monitor-result "${MONITOR_RESULT}" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" \
  --clock-bridge "${PROCESSED_DIR}/clock_bridge.json" \
  --oracle "${PROCESSED_DIR}/route_oracle.json" \
  --output "${PROCESSED_DIR}/experiment_result.json"
python3 "${REPO_ROOT}/scripts/tracing/compact_route_trace.py" \
  --input "${PROCESSED_DIR}/route_trace.jsonl" \
  --output "${PROCESSED_DIR}/route_trace.compact.jsonl" \
  --stride 10 --report "${PROCESSED_DIR}/trace_compaction.json" \
  --summary "${PROCESSED_DIR}/route_summary.json"
mv "${PROCESSED_DIR}/route_trace.compact.jsonl" "${PROCESSED_DIR}/route_trace.jsonl"

echo "ROUTE_EXPERIMENT=PASS kind=${EXPERIMENT_KIND} object=${OBJECT} run_id=${RUN_ID}"
