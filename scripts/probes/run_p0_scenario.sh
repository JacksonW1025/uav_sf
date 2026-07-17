#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCENARIO="${1:-}"
RUN_ID="${2:-}"
if [[ ! "${SCENARIO}" =~ ^(offboard|external|executor)$ ]] || [[ -z "${RUN_ID}" ]]; then
  echo "usage: $0 {offboard|external|executor} RUN_ID" >&2
  exit 2
fi

set +u
source "${ROS_DISTRO_SETUP:-/opt/ros/jazzy/setup.bash}"
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/ros2_ws/install/setup.bash}"
set -u

PX4_DIR="${PX4_OBSERVABILITY_DIR:-${REPO_ROOT}/external/PX4-Autopilot-route-observability}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_PREFIX="${REPO_ROOT}/external/install/microxrce_agent"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-${AGENT_PREFIX}/bin/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-${AGENT_PREFIX}/lib}"
EXTERNAL_MODE_BIN="${ROUTE_EXTERNAL_MODE_BIN:-${REPO_ROOT}/ros2_ws/install/route_transition_external_mode/lib/route_transition_external_mode/route_transition_external_mode}"
RAW_DIR="${P0_RUN_ROOT:-${REPO_ROOT}/runs/p0}/${RUN_ID}/raw"
PROCESSED_DIR="${P0_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/p0}/${RUN_ID}"
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"
START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"
# PX4 persists reboot-required logger parameters in the generated SITL rootfs.
# Start each controlled repeat from the locked defaults, then apply this script's
# explicit scenario parameters, so a prior D-gate run cannot contaminate P0.
rm -f "${PX4_BUILD}/rootfs/0/parameters.bson" \
  "${PX4_BUILD}/rootfs/0/parameters_backup.bson"

PX4_PID=""
AGENT_PID=""
MODE_PID=""
RUNNER_PID=""
FIFO="${RAW_DIR}/px4.stdin"
rm -f "${FIFO}"
mkfifo "${FIFO}"
exec 3<>"${FIFO}"

stop_process() {
  local pid="${1:-}"
  local signal="${2:-TERM}"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
    return
  fi
  kill -"${signal}" "${pid}" 2>/dev/null || true
  for _ in $(seq 1 50); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -TERM "${pid}" 2>/dev/null || true
    for _ in $(seq 1 50); do
      kill -0 "${pid}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    kill -KILL "${pid}" 2>/dev/null || true
  fi
  wait "${pid}" 2>/dev/null || true
}

finish_processes() {
  set +e
  stop_process "${MODE_PID}" INT
  stop_process "${RUNNER_PID}" INT
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then
    echo shutdown >&3
    for _ in $(seq 1 100); do
      kill -0 "${PX4_PID}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  while read -r gz_pid; do
    stop_process "${gz_pid}" TERM
  done < <(pgrep -P "$$" -f '^gz sim ' 2>/dev/null || true)
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}"
}
trap finish_processes EXIT

LD_LIBRARY_PATH="${AGENT_LIBRARY_PATH}" \
  "${AGENT_BIN}" udp4 -p 8888 \
  >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!

(
  cd "${PX4_DIR}"
  # Do not let a caller's Gazebo resource path select a model from another PX4
  # checkout. px4-rc.gzsim adds this checkout's locked model/world paths.
  GZ_SIM_RESOURCE_PATH= PX4_PARAM_SDLOG_MODE=0 PX4_PARAM_SDLOG_PROFILE=1 \
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
sleep 2

RESULT_FILE="${RAW_DIR}/runner_result.json"
runner_args=(--scenario offboard --output "${RESULT_FILE}" --timeout 180)
if [[ -n "${P0_ACTIVE_DURATION_S:-}" ]]; then
  runner_args+=(--active-duration "${P0_ACTIVE_DURATION_S}")
fi
if [[ "${P0_HOVER_ONLY:-0}" == "1" ]]; then
  runner_args+=(--hover-only)
fi
if [[ -n "${P0_ACTIVE_DURATION_S:-}" ]]; then
  export UAV_SF_ACTIVE_DURATION_S="${P0_ACTIVE_DURATION_S}"
fi
case "${SCENARIO}" in
  offboard)
    python3 "${REPO_ROOT}/scripts/probes/p0_route_runner.py" "${runner_args[@]}" \
      >"${RAW_DIR}/runner.log" 2>&1
    ;;
  external)
    external_runner_args=(--scenario external --output "${RESULT_FILE}" --timeout 180)
    if [[ -n "${P0_ACTIVE_DURATION_S:-}" ]]; then
      external_runner_args+=(--active-duration "${P0_ACTIVE_DURATION_S}")
    fi
    python3 "${REPO_ROOT}/scripts/probes/p0_route_runner.py" "${external_runner_args[@]}" \
      >"${RAW_DIR}/runner.log" 2>&1 &
    RUNNER_PID=$!
    "${EXTERNAL_MODE_BIN}" \
      >"${RAW_DIR}/external_mode.log" 2>&1 &
    MODE_PID=$!
    wait "${RUNNER_PID}"
    RUNNER_PID=""
    ;;
  executor)
    python3 "${REPO_ROOT}/scripts/probes/p0_route_runner.py" \
      --scenario monitor --output "${RESULT_FILE}" --timeout 180 \
      >"${RAW_DIR}/runner.log" 2>&1 &
    RUNNER_PID=$!
    "${REPO_ROOT}/ros2_ws/install/route_transition_external_mode/lib/route_transition_external_mode/p0_external_mode_executor" \
      >"${RAW_DIR}/external_mode_executor.log" 2>&1 &
    MODE_PID=$!
    wait "${RUNNER_PID}"
    RUNNER_PID=""
    ;;
esac

echo shutdown >&3
for _ in $(seq 1 200); do
  kill -0 "${PX4_PID}" 2>/dev/null || break
  sleep 0.1
done
if kill -0 "${PX4_PID}" 2>/dev/null; then
  echo "PX4 did not exit after the normal shutdown command" >&2
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

collector_args=(
  --ulog "${RAW_DIR}/flight.ulg"
  --output "${PROCESSED_DIR}/route_trace.jsonl"
  --run-id "${RUN_ID}"
  --producer-events "${RAW_DIR}/producer_events.jsonl"
)
if [[ -f "${RAW_DIR}/external_mode.log" ]]; then
  collector_args+=(--lifecycle-log "${RAW_DIR}/external_mode.log")
elif [[ -f "${RAW_DIR}/external_mode_executor.log" ]]; then
  collector_args+=(--lifecycle-log "${RAW_DIR}/external_mode_executor.log")
fi
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" "${collector_args[@]}"
CLOCK_BRIDGE="${PROCESSED_DIR}/clock_bridge.json"
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${RAW_DIR}/producer_events.jsonl" \
  --output "${CLOCK_BRIDGE}" || true
summary_args=(
  --trace "${PROCESSED_DIR}/route_trace.jsonl"
  --result "${RESULT_FILE}"
  --output "${PROCESSED_DIR}/route_summary.json"
  --scenario-label "${SCENARIO}"
  --source "${RAW_DIR}/flight.ulg"
  --source "${RAW_DIR}/producer_events.jsonl"
  --clock-bridge "${CLOCK_BRIDGE}"
)
if [[ -f "${RAW_DIR}/external_mode.log" ]]; then
  summary_args+=(--source "${RAW_DIR}/external_mode.log")
elif [[ -f "${RAW_DIR}/external_mode_executor.log" ]]; then
  summary_args+=(--source "${RAW_DIR}/external_mode_executor.log")
fi
if [[ -n "${P0_OBSERVATION_PROFILE:-}" ]]; then
  summary_args+=(--observation-profile "${P0_OBSERVATION_PROFILE}")
fi
if [[ -n "${P0_UORB_QUEUE_LENGTH:-}" ]]; then
  summary_args+=(--uorb-queue-length "${P0_UORB_QUEUE_LENGTH}")
fi
if [[ -n "${P0_BUILD_PROVENANCE:-}" ]]; then
  summary_args+=(--build-provenance "${P0_BUILD_PROVENANCE}")
fi
python3 "${REPO_ROOT}/scripts/analysis/summarize_route_trace.py" "${summary_args[@]}"
python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" \
  --trace "${PROCESSED_DIR}/route_trace.jsonl" \
  --clock-bridge "${CLOCK_BRIDGE}" \
  --output "${PROCESSED_DIR}/route_oracle.json"

echo "P0_SCENARIO=PASS scenario=${SCENARIO} run_id=${RUN_ID}"
