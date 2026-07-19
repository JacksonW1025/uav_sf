#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${1:-}"
if [[ ! "${RUN_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "usage: $0 RUN_ID" >&2
  exit 2
fi

set +u
# shellcheck disable=SC1090
source "${ROS_DISTRO_SETUP:-/opt/ros/humble/setup.bash}"
# shellcheck disable=SC1090
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/ros2_ws_humble_live/install/setup.bash}"
set -u

PX4_DIR="${SUCCESSOR_PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-control}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-/usr/local/bin/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-/usr/local/lib}"
EXECUTOR_BIN="${SUCCESSOR_EXECUTOR_BIN:-${REPO_ROOT}/ros2_ws_humble_live/install/route_transition_external_mode/lib/route_transition_external_mode/successor_baseline_executor}"
LIBRARY_BIN="${SUCCESSOR_LIBRARY_BIN:-${REPO_ROOT}/ros2_ws_humble_live/install/px4_ros2_cpp/lib/libpx4_ros2_cpp.so}"
LOGGER_TOPICS_FILE="${SUCCESSOR_LOGGER_TOPICS_FILE:-${REPO_ROOT}/config/phase_a2_minimal_logger_topics.txt}"
BUILD_PROVENANCE="${SUCCESSOR_BUILD_PROVENANCE:-${REPO_ROOT}/experiments/motivation/successor/baseline_build_provenance.json}"
PROFILE="${SUCCESSOR_PROFILE:-${REPO_ROOT}/experiments/motivation/successor/baseline_lifecycle_profile.yaml}"
SIMULATION_SEED="${SUCCESSOR_SIMULATION_SEED:-16201}"
ACTIVE_DURATION_S="${SUCCESSOR_ACTIVE_DURATION_S:-5}"
RAW_PARENT="${SUCCESSOR_RUN_ROOT:-${REPO_ROOT}/runs/motivation/successor/baseline}"
PROCESSED_PARENT="${SUCCESSOR_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/motivation/successor/baseline}"
RAW_DIR="${RAW_PARENT}/${RUN_ID}/raw"
PROCESSED_DIR="${PROCESSED_PARENT}/${RUN_ID}"

sha_matches() {
  local path="$1"
  local expected="$2"
  [[ -f "${path}" ]] && [[ "$(sha256sum "${path}" | awk '{print $1}')" == "${expected}" ]]
}

[[ -x "${AGENT_BIN}" ]] || { echo "MicroXRCEAgent is unavailable" >&2; exit 4; }
[[ -x "${EXECUTOR_BIN}" ]] || { echo "successor baseline executable is unavailable" >&2; exit 4; }
[[ -f "${LIBRARY_BIN}" ]] || { echo "px4_ros2_cpp library is unavailable" >&2; exit 4; }
[[ -x "${PX4_BUILD}/bin/px4" ]] || { echo "PX4 SITL binary is unavailable" >&2; exit 4; }
[[ "$(git -C "${PX4_DIR}" rev-parse HEAD)" == "4ae21a5e569d3d89c2f6366688cbacb3e93437c9" ]] \
  || { echo "PX4 revision differs from baseline lock" >&2; exit 5; }
[[ "$(git -C "${REPO_ROOT}/ros2_ws/src/px4_ros2_interface_lib" rev-parse HEAD)" == "c3e410f035806e8c56246708432ded09c976434b" ]] \
  || { echo "px4_ros2_interface_lib source revision differs from baseline lock" >&2; exit 5; }
sha_matches "${PX4_BUILD}/bin/px4" "931320a07585dabf36ca9c8ba994756b93ee7d154cd9c8930b2171548d978993" \
  || { echo "PX4 binary differs from baseline lock" >&2; exit 5; }
sha_matches "${LIBRARY_BIN}" "dddfa0698c27617ce5a368dc7d0d5272bc510f3cb780c5ef3f48c77d098380e6" \
  || { echo "px4_ros2_cpp binary differs from baseline lock" >&2; exit 5; }
sha_matches "${REPO_ROOT}/experiments/probes/p5/p5_v6_differential_gate.json" \
  "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc" \
  || { echo "protected P5 v6 Gate changed" >&2; exit 5; }
sha_matches "${REPO_ROOT}/experiments/probes/p5/campaign_seeded_v6_manifest.json" \
  "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518" \
  || { echo "protected P5 v6 manifest changed" >&2; exit 5; }
grep -aF "A mode executor cannot be used in combination with a mode that replaces an internal mode" "${LIBRARY_BIN}" >/dev/null \
  || { echo "current constructor prevention guard is absent" >&2; exit 5; }
if ! git -C "${REPO_ROOT}" diff --quiet || ! git -C "${REPO_ROOT}" diff --cached --quiet; then
  echo "tracked repository changes must be committed before a formal baseline attempt" >&2
  exit 6
fi
if command -v ss >/dev/null 2>&1; then
  LISTEN_ADDRESSES="$(ss -H -lun | awk '{print $5}')"
  if grep -E '(^|:)8888$' <<<"${LISTEN_ADDRESSES}" >/dev/null; then
    echo "UDP port 8888 is already occupied" >&2
    exit 7
  fi
fi
if [[ -e "${RAW_DIR}" || -e "${PROCESSED_DIR}" ]]; then
  echo "run_id already has an artifact directory: ${RUN_ID}" >&2
  exit 3
fi
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"

LOGGER_TOPICS_TARGET="${PX4_BUILD}/rootfs/0/etc/logging/logger_topics.txt"
LOGGER_TOPICS_BACKUP="${RAW_DIR}/logger_topics.previous"
LOGGER_TOPICS_EXISTED=0
if [[ -f "${LOGGER_TOPICS_TARGET}" ]]; then
  cp "${LOGGER_TOPICS_TARGET}" "${LOGGER_TOPICS_BACKUP}"
  LOGGER_TOPICS_EXISTED=1
fi
install -D -m 0644 "${LOGGER_TOPICS_FILE}" "${LOGGER_TOPICS_TARGET}"

START_MARKER="${RAW_DIR}/run.start"
touch "${START_MARKER}"
rm -f "${PX4_BUILD}/rootfs/0/parameters.bson" \
  "${PX4_BUILD}/rootfs/0/parameters_backup.bson"

PX4_PID=""
AGENT_PID=""
EXECUTOR_PID=""
MONITOR_PID=""
GZ_PID=""
GZ_PARTITION_NAME="uav_sf_successor_${RUN_ID//[^a-zA-Z0-9_]/_}"
FIFO="${RAW_DIR}/px4.stdin"
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
  stop_process "${EXECUTOR_PID}" INT
  stop_process "${MONITOR_PID}" INT
  if [[ -n "${PX4_PID}" ]] && kill -0 "${PX4_PID}" 2>/dev/null; then
    echo shutdown >&3
    for _ in $(seq 1 100); do
      kill -0 "${PX4_PID}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  while read -r child_pid; do
    stop_process "${child_pid}" TERM
  done < <(pgrep -P "$$" -f '^gz sim ' 2>/dev/null || true)
  stop_process "${GZ_PID}" TERM
  stop_process "${AGENT_PID}" TERM
  exec 3>&-
  rm -f "${FIFO}" "${PX4_BUILD}/rootfs/0/parameters.bson" \
    "${PX4_BUILD}/rootfs/0/parameters_backup.bson"
  if [[ "${LOGGER_TOPICS_EXISTED}" == "1" ]]; then
    cp "${LOGGER_TOPICS_BACKUP}" "${LOGGER_TOPICS_TARGET}"
  else
    rm -f "${LOGGER_TOPICS_TARGET}"
  fi
}
trap finish_processes EXIT

LD_LIBRARY_PATH="${AGENT_LIBRARY_PATH}" "${AGENT_BIN}" udp4 -p 8888 \
  >"${RAW_DIR}/microxrce_agent.log" 2>&1 &
AGENT_PID=$!

(
  export GZ_SIM_RESOURCE_PATH=
  export GZ_SIM_SYSTEM_PLUGIN_PATH=
  export GZ_SIM_SERVER_CONFIG_PATH=
  set +u
  # shellcheck disable=SC1091
  source "${PX4_BUILD}/rootfs/gz_env.sh"
  set -u
  exec env GZ_PARTITION="${GZ_PARTITION_NAME}" gz sim --seed "${SIMULATION_SEED}" \
    --verbose=1 -r -s "${PX4_DIR}/Tools/simulation/gz/worlds/default.sdf"
) >"${RAW_DIR}/gazebo.log" 2>&1 &
GZ_PID=$!
for _ in $(seq 1 100); do
  GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null | grep -F '/world/default/clock' >/dev/null && break
  kill -0 "${GZ_PID}" 2>/dev/null || { echo "Gazebo exited before readiness" >&2; exit 10; }
  sleep 0.1
done
GZ_PARTITION="${GZ_PARTITION_NAME}" gz topic -l 2>/dev/null \
  | grep -F '/world/default/clock' >/dev/null || { echo "Gazebo readiness timeout" >&2; exit 10; }

(
  cd "${PX4_DIR}"
  GZ_PARTITION="${GZ_PARTITION_NAME}" PX4_GZ_STANDALONE=1 GZ_SIM_RESOURCE_PATH='' \
    PX4_PARAM_SDLOG_MODE=0 PX4_PARAM_SDLOG_PROFILE=0 HEADLESS=1 PX4_SIM_MODEL=gz_x500 \
    "${PX4_BUILD}/bin/px4" -i 0 <"${FIFO}"
) >"${RAW_DIR}/px4.log" 2>&1 &
PX4_PID=$!

for _ in $(seq 1 120); do
  grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null && break
  kill -0 "${PX4_PID}" 2>/dev/null || { echo "PX4 exited before shell readiness" >&2; exit 10; }
  sleep 0.25
done
grep -q "pxh>" "${RAW_DIR}/px4.log" 2>/dev/null \
  || { echo "PX4 shell readiness timeout" >&2; exit 10; }

echo "param set COM_RC_IN_MODE 4" >&3
echo "param set NAV_RCL_ACT 0" >&3
echo "param set NAV_DLL_ACT 0" >&3
echo "param set COM_ARM_WO_GPS 1" >&3
sleep 2

MONITOR_RESULT="${RAW_DIR}/monitor_result.json"
LIFECYCLE_EVENTS="${RAW_DIR}/lifecycle_events.jsonl"
python3 "${REPO_ROOT}/scripts/tracing/successor_lifecycle_monitor.py" \
  --run-id "${RUN_ID}" --output "${MONITOR_RESULT}" --events "${LIFECYCLE_EVENTS}" \
  --timeout 180 --post-disarm-capture 8 --component-name "Successor Baseline" \
  >"${RAW_DIR}/monitor.log" 2>&1 &
MONITOR_PID=$!
sleep 1
UAV_SF_SUCCESSOR_ACTIVE_DURATION_S="${ACTIVE_DURATION_S}" "${EXECUTOR_BIN}" \
  >"${RAW_DIR}/external_mode_executor.log" 2>&1 &
EXECUTOR_PID=$!

set +e
wait "${MONITOR_PID}"
MONITOR_RC=$?
set -e
MONITOR_PID=""
stop_process "${EXECUTOR_PID}" INT
EXECUTOR_PID=""

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

ULOG="$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -nr | sed -n '1p' | cut -d' ' -f2-)"
if [[ -z "${ULOG}" || ! -f "${ULOG}" ]]; then
  echo "No ULog was produced for ${RUN_ID}" >&2
  exit 12
fi
cp "${ULOG}" "${RAW_DIR}/flight.ulg"

ROUTE_TRACE="${PROCESSED_DIR}/route_trace.jsonl"
CLOCK_BRIDGE="${PROCESSED_DIR}/clock_bridge.json"
ROUTE_ORACLE="${PROCESSED_DIR}/route_oracle.json"
SUCCESSOR_ORACLE="${PROCESSED_DIR}/successor_oracle.json"
ATTEMPT_RESULT="${PROCESSED_DIR}/attempt_result.json"
python3 "${REPO_ROOT}/scripts/tracing/route_trace_collector.py" \
  --ulog "${RAW_DIR}/flight.ulg" --output "${ROUTE_TRACE}" --run-id "${RUN_ID}" \
  --producer-events "${LIFECYCLE_EVENTS}" \
  --lifecycle-log "${RAW_DIR}/external_mode_executor.log"

set +e
python3 "${REPO_ROOT}/scripts/tracing/clock_bridge_collector.py" \
  --samples "${LIFECYCLE_EVENTS}" --output "${CLOCK_BRIDGE}"
CLOCK_RC=$?
set -e

python3 "${REPO_ROOT}/scripts/analysis/summarize_route_trace.py" \
  --trace "${ROUTE_TRACE}" --result "${MONITOR_RESULT}" \
  --output "${PROCESSED_DIR}/route_summary.json" \
  --scenario-label "successor_baseline" \
  --source "${RAW_DIR}/flight.ulg" --source "${LIFECYCLE_EVENTS}" \
  --source "${RAW_DIR}/external_mode_executor.log" --clock-bridge "${CLOCK_BRIDGE}" \
  --observation-profile TRANSITION --uorb-queue-length 4 \
  --build-provenance "${BUILD_PROVENANCE}"

MODE_ID=""
if [[ -f "${MONITOR_RESULT}" ]]; then
  MODE_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])).get("registered_mode_id"); print(value if isinstance(value, int) else "")' "${MONITOR_RESULT}")"
fi
ROUTE_RC=1
SUCCESSOR_RC=1
if [[ "${MODE_ID}" =~ ^[0-9]+$ ]]; then
  set +e
  python3 "${REPO_ROOT}/scripts/oracles/route_oracle_v0.py" \
    --trace "${ROUTE_TRACE}" --clock-bridge "${CLOCK_BRIDGE}" \
    --output "${ROUTE_ORACLE}" --transition-source-mode "${MODE_ID}" \
    --transition-target-mode 18 --source-artifact-complete
  ROUTE_RC=$?
  set -e
fi
if [[ -f "${ROUTE_ORACLE}" && -f "${CLOCK_BRIDGE}" ]]; then
  set +e
  python3 "${REPO_ROOT}/scripts/oracles/successor_progression_oracle.py" \
    --lifecycle-events "${LIFECYCLE_EVENTS}" \
    --executor-log "${RAW_DIR}/external_mode_executor.log" \
    --route-trace "${ROUTE_TRACE}" --route-oracle "${ROUTE_ORACLE}" \
    --clock-bridge "${CLOCK_BRIDGE}" --profile "${PROFILE}" \
    --output "${SUCCESSOR_ORACLE}"
  SUCCESSOR_RC=$?
  set -e
fi

set +e
python3 "${REPO_ROOT}/scripts/analysis/classify_successor_baseline.py" \
  --run-id "${RUN_ID}" --monitor "${MONITOR_RESULT}" \
  --clock-bridge "${CLOCK_BRIDGE}" --route-oracle "${ROUTE_ORACLE}" \
  --successor-oracle "${SUCCESSOR_ORACLE}" --lifecycle-events "${LIFECYCLE_EVENTS}" \
  --executor-log "${RAW_DIR}/external_mode_executor.log" --route-trace "${ROUTE_TRACE}" \
  --flight-log "${RAW_DIR}/flight.ulg" --executor-binary "${EXECUTOR_BIN}" \
  --library-binary "${LIBRARY_BIN}" --px4-dir "${PX4_DIR}" --output "${ATTEMPT_RESULT}"
CLASSIFIER_RC=$?
set -e

if [[ "${MONITOR_RC}" != "0" || "${CLOCK_RC}" != "0" || "${ROUTE_RC}" != "0" \
      || "${SUCCESSOR_RC}" != "0" || "${CLASSIFIER_RC}" != "0" ]]; then
  echo "SUCCESSOR_BASELINE=REJECTED run_id=${RUN_ID} monitor_rc=${MONITOR_RC} clock_rc=${CLOCK_RC} route_rc=${ROUTE_RC} successor_rc=${SUCCESSOR_RC}" >&2
  exit 20
fi
echo "SUCCESSOR_BASELINE=ACCEPTED run_id=${RUN_ID}"
