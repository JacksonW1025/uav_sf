#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${1:-}"
if [[ ! "${RUN_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "usage: $0 RUN_ID" >&2
  exit 2
fi

HISTORY_ROOT="${SUCCESSOR_HISTORY_ROOT:-${REPO_ROOT}/external/issue162_history}"
PX4_DIR="${SUCCESSOR_PX4_DIR:-${HISTORY_ROOT}/PX4-Autopilot-v1.16.0}"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
ROOTFS="${SUCCESSOR_JAZZY_ROOTFS:-${HISTORY_ROOT}/noble-rootfs}"
JAZZY_WS="${SUCCESSOR_JAZZY_WS:-${HISTORY_ROOT}/ros2_ws_jazzy}"
LIBRARY_SOURCE="${SUCCESSOR_LIBRARY_SOURCE:-${HISTORY_ROOT}/px4_ros2_interface_lib-a5b9f3c}"
EXECUTOR_BIN="${SUCCESSOR_EXECUTOR_BIN:-${JAZZY_WS}/install/lib/route_transition_external_mode/issue162_replay}"
LIBRARY_BIN="${SUCCESSOR_LIBRARY_BIN:-${JAZZY_WS}/install/lib/libpx4_ros2_cpp.so}"
AGENT_BIN="${MICROXRCE_AGENT_BIN:-/usr/local/bin/MicroXRCEAgent}"
AGENT_LIBRARY_PATH="${MICROXRCE_AGENT_LD_LIBRARY_PATH:-/usr/local/lib}"
LOGGER_TOPICS_FILE="${SUCCESSOR_LOGGER_TOPICS_FILE:-${REPO_ROOT}/config/phase_a2_minimal_logger_topics.txt}"
BUILD_PROVENANCE="${SUCCESSOR_BUILD_PROVENANCE:-${REPO_ROOT}/experiments/motivation/successor/historical_replay_build_provenance.json}"
PROFILE="${SUCCESSOR_PROFILE:-${REPO_ROOT}/experiments/motivation/successor/historical_lifecycle_profile.yaml}"
SIMULATION_SEED="${SUCCESSOR_SIMULATION_SEED:-16211}"
RAW_PARENT="${SUCCESSOR_RUN_ROOT:-${REPO_ROOT}/runs/motivation/successor/historical}"
PROCESSED_PARENT="${SUCCESSOR_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/motivation/successor/historical}"
RAW_DIR="${RAW_PARENT}/${RUN_ID}/raw"
PROCESSED_DIR="${PROCESSED_PARENT}/${RUN_ID}"

sha_matches() {
  local path="$1"
  local expected="$2"
  [[ -f "${path}" ]] && [[ "$(sha256sum "${path}" | awk '{print $1}')" == "${expected}" ]]
}

run_jazzy() {
  bwrap --unshare-user --uid 0 --gid 0 \
    --bind "${ROOTFS}" / --dev /dev --proc /proc --ro-bind /sys /sys \
    --ro-bind /etc/resolv.conf /etc/resolv.conf \
    --dir /mnt/nvme --bind "${REPO_ROOT}" "${REPO_ROOT}" --share-net --clearenv \
    --setenv HOME /root \
    --setenv PATH /opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    --setenv LANG C.UTF-8 --chdir "${REPO_ROOT}" \
    /bin/bash -lc 'source /opt/ros/jazzy/setup.bash && source "$1/install/setup.bash" && shift && exec "$@"' \
    historical-jazzy "${JAZZY_WS}" "$@"
}

[[ -x "${AGENT_BIN}" ]] || { echo "MicroXRCEAgent is unavailable" >&2; exit 4; }
[[ -x "${EXECUTOR_BIN}" ]] || { echo "historical replay executable is unavailable" >&2; exit 4; }
[[ -f "${LIBRARY_BIN}" ]] || { echo "historical px4_ros2_cpp library is unavailable" >&2; exit 4; }
[[ -x "${PX4_BUILD}/bin/px4" ]] || { echo "historical PX4 SITL binary is unavailable" >&2; exit 4; }
[[ -f "${ROOTFS}/opt/ros/jazzy/setup.bash" ]] || { echo "isolated Jazzy rootfs is unavailable" >&2; exit 4; }
[[ "$(git -C "${PX4_DIR}" rev-parse HEAD)" == "6ea3539157ca358c70a515878b77077af7d4611d" ]] \
  || { echo "PX4 revision differs from historical lock" >&2; exit 5; }
[[ "$(git -C "${LIBRARY_SOURCE}" rev-parse HEAD)" == "a5b9f3cb7cb65d2be80183bad31e9a7ce9f02684" ]] \
  || { echo "library revision differs from historical lock" >&2; exit 5; }
sha_matches "${PX4_BUILD}/bin/px4" "$(jq -r .historical_px4.binary_sha256 "${BUILD_PROVENANCE}")" \
  || { echo "PX4 binary differs from historical build provenance" >&2; exit 5; }
sha_matches "${LIBRARY_BIN}" "$(jq -r .px4_ros2_interface_lib_binary_sha256 "${BUILD_PROVENANCE}")" \
  || { echo "historical library differs from build provenance" >&2; exit 5; }
sha_matches "${EXECUTOR_BIN}" "$(jq -r .adapter_binary_sha256 "${BUILD_PROVENANCE}")" \
  || { echo "historical replay executable differs from build provenance" >&2; exit 5; }
[[ "$(git -C "${PX4_DIR}" diff --cached | sha256sum | awk '{print $1}')" == "$(jq -r .historical_px4.observation_patch.diff_sha256 "${BUILD_PROVENANCE}")" ]] \
  || { echo "historical PX4 observation diff differs from provenance" >&2; exit 5; }
sha_matches "${REPO_ROOT}/experiments/probes/p5/p5_v6_differential_gate.json" \
  "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc" \
  || { echo "protected P5 v6 Gate changed" >&2; exit 5; }
sha_matches "${REPO_ROOT}/experiments/probes/p5/campaign_seeded_v6_manifest.json" \
  "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518" \
  || { echo "protected P5 v6 manifest changed" >&2; exit 5; }
if ! git -C "${REPO_ROOT}" diff --quiet || ! git -C "${REPO_ROOT}" diff --cached --quiet; then
  echo "tracked repository changes must be committed before a formal historical replay" >&2
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

PX4_INSTANCE_ROOT="${PX4_BUILD}/rootfs/0"
PX4_INSTANCE_ETC="${PX4_INSTANCE_ROOT}/etc"
mkdir -p "${PX4_INSTANCE_ROOT}"
if [[ -L "${PX4_INSTANCE_ETC}" ]]; then
  [[ "$(readlink -f "${PX4_INSTANCE_ETC}")" == "$(readlink -f "${PX4_BUILD}/etc")" ]] \
    || { echo "historical PX4 instance etc link has the wrong target" >&2; exit 8; }
elif [[ -e "${PX4_INSTANCE_ETC}" ]]; then
  echo "historical PX4 instance etc path exists but is not a symlink" >&2
  exit 8
else
  ln -s "${PX4_BUILD}/etc" "${PX4_INSTANCE_ETC}"
fi
[[ -f "${PX4_INSTANCE_ETC}/init.d-posix/rcS" ]] \
  || { echo "historical PX4 instance startup script is unavailable" >&2; exit 8; }

LOGGER_TOPICS_TARGET="${PX4_INSTANCE_ETC}/logging/logger_topics.txt"
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
GZ_PARTITION_NAME="uav_sf_issue162_${RUN_ID//[^a-zA-Z0-9_]/_}"
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
ABORT_MARKER="${RAW_DIR}/infrastructure.abort"
run_jazzy python3 "${REPO_ROOT}/scripts/tracing/successor_lifecycle_monitor.py" \
  --run-id "${RUN_ID}" --output "${MONITOR_RESULT}" --events "${LIFECYCLE_EVENTS}" \
  --timeout 180 --post-disarm-capture 8 --post-completion-capture 8 \
  --component-name "Issue 162 Custom RTL" --abort-marker "${ABORT_MARKER}" \
  >"${RAW_DIR}/monitor.log" 2>&1 &
MONITOR_PID=$!
MIN_PRELAUNCH_CLOCK_SAMPLES="${SUCCESSOR_MIN_PRELAUNCH_CLOCK_SAMPLES:-40}"
OBSERVED_CLOCK_SAMPLES=0
for _ in $(seq 1 600); do
  OBSERVED_CLOCK_SAMPLES="$(grep -c '"event_type": "clock_bridge_sample"' "${LIFECYCLE_EVENTS}" 2>/dev/null || true)"
  [[ "${OBSERVED_CLOCK_SAMPLES}" -ge "${MIN_PRELAUNCH_CLOCK_SAMPLES}" ]] && break
  kill -0 "${PX4_PID}" 2>/dev/null || { echo "PX4 exited during clock warmup" >&2; exit 13; }
  kill -0 "${MONITOR_PID}" 2>/dev/null || { echo "lifecycle monitor exited during clock warmup" >&2; exit 13; }
  sleep 0.1
done
[[ "${OBSERVED_CLOCK_SAMPLES}" -ge "${MIN_PRELAUNCH_CLOCK_SAMPLES}" ]] \
  || { echo "clock warmup did not reach ${MIN_PRELAUNCH_CLOCK_SAMPLES} samples" >&2; exit 13; }

run_jazzy "${EXECUTOR_BIN}" >"${RAW_DIR}/external_mode_executor.log" 2>&1 &
EXECUTOR_PID=$!
TRIGGER_FAILURE=0
for _ in $(seq 1 300); do
  grep -q '"event_type": "registration_observed"' "${LIFECYCLE_EVENTS}" 2>/dev/null && break
  if ! kill -0 "${EXECUTOR_PID}" 2>/dev/null; then
    TRIGGER_FAILURE=1
    break
  fi
  sleep 0.1
done
if ! grep -q '"event_type": "registration_observed"' "${LIFECYCLE_EVENTS}" 2>/dev/null; then
  TRIGGER_FAILURE=1
  printf '%s\n' "historical mode/executor registration was not observed before trigger" >"${ABORT_MARKER}"
else
  echo "commander arm" >&3
  sleep 2
  echo "commander takeoff" >&3
  AIRBORNE=0
  for _ in $(seq 1 400); do
    if jq -e 'select(.armed == true and .landed == false)' "${LIFECYCLE_EVENTS}" >/dev/null 2>&1; then
      AIRBORNE=1
      break
    fi
    kill -0 "${PX4_PID}" 2>/dev/null || break
    kill -0 "${EXECUTOR_PID}" 2>/dev/null || break
    sleep 0.1
  done
  if [[ "${AIRBORNE}" == "1" ]]; then
    sleep 2
    echo "commander mode auto:rtl" >&3
  else
    TRIGGER_FAILURE=1
    printf '%s\n' "vehicle did not become armed and airborne before RTL trigger" >"${ABORT_MARKER}"
  fi
fi

PX4_EARLY_EXIT=0
EXECUTOR_EARLY_EXIT=0
while kill -0 "${MONITOR_PID}" 2>/dev/null; do
  if ! kill -0 "${PX4_PID}" 2>/dev/null; then
    PX4_EARLY_EXIT=1
    printf '%s\n' "infrastructure process exited: PX4 before lifecycle window completed" >"${ABORT_MARKER}"
    break
  fi
  if ! kill -0 "${EXECUTOR_PID}" 2>/dev/null; then
    EXECUTOR_EARLY_EXIT=1
    printf '%s\n' "infrastructure process exited: replay harness before lifecycle window completed" >"${ABORT_MARKER}"
    break
  fi
  sleep 0.1
done
set +e
wait "${MONITOR_PID}"
MONITOR_RC=$?
set -e
MONITOR_PID=""
EXECUTOR_RC=0
if [[ "${EXECUTOR_EARLY_EXIT}" == "1" ]]; then
  set +e
  wait "${EXECUTOR_PID}"
  EXECUTOR_RC=$?
  set -e
else
  stop_process "${EXECUTOR_PID}" INT
fi
EXECUTOR_PID=""

PX4_RC=0
if [[ "${PX4_EARLY_EXIT}" == "0" ]]; then
  echo shutdown >&3
  for _ in $(seq 1 200); do
    kill -0 "${PX4_PID}" 2>/dev/null || break
    sleep 0.1
  done
  kill -0 "${PX4_PID}" 2>/dev/null && { echo "PX4 did not exit after normal shutdown" >&2; exit 11; }
fi
set +e
wait "${PX4_PID}"
PX4_RC=$?
set -e
PX4_PID=""
sleep 1

ULOG="$(find "${PX4_BUILD}/rootfs/0/log" -type f -name '*.ulg' -newer "${START_MARKER}" -printf '%T@ %p\n' 2>/dev/null | sort -nr | sed -n '1p' | cut -d' ' -f2-)"
[[ -n "${ULOG}" && -f "${ULOG}" ]] || { echo "No ULog was produced for ${RUN_ID}" >&2; exit 12; }
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
  --output "${PROCESSED_DIR}/route_summary.json" --scenario-label "issue162_historical" \
  --source "${RAW_DIR}/flight.ulg" --source "${LIFECYCLE_EVENTS}" \
  --source "${RAW_DIR}/external_mode_executor.log" --clock-bridge "${CLOCK_BRIDGE}" \
  --observation-profile TRANSITION --uorb-queue-length 4 \
  --build-provenance "${BUILD_PROVENANCE}"

MODE_ID="$(jq -r '.registered_mode_id // empty' "${MONITOR_RESULT}")"
ROUTE_RC=1
SUCCESSOR_RC=2
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
python3 "${REPO_ROOT}/scripts/analysis/classify_successor_historical_replay.py" \
  --run-id "${RUN_ID}" --monitor "${MONITOR_RESULT}" \
  --clock-bridge "${CLOCK_BRIDGE}" --route-oracle "${ROUTE_ORACLE}" \
  --successor-oracle "${SUCCESSOR_ORACLE}" --lifecycle-events "${LIFECYCLE_EVENTS}" \
  --executor-log "${RAW_DIR}/external_mode_executor.log" --route-trace "${ROUTE_TRACE}" \
  --flight-log "${RAW_DIR}/flight.ulg" --executor-binary "${EXECUTOR_BIN}" \
  --library-binary "${LIBRARY_BIN}" --library-source-dir "${LIBRARY_SOURCE}" \
  --px4-dir "${PX4_DIR}" --build-provenance "${BUILD_PROVENANCE}" \
  --monitor-exit-code "${MONITOR_RC}" --px4-exit-code "${PX4_RC}" \
  --executor-exit-code "${EXECUTOR_RC}" --px4-early-exit "${PX4_EARLY_EXIT}" \
  --executor-early-exit "${EXECUTOR_EARLY_EXIT}" --trigger-failure "${TRIGGER_FAILURE}" \
  --output "${ATTEMPT_RESULT}"
CLASSIFIER_RC=$?
set -e
if [[ "${CLOCK_RC}" != "0" || "${ROUTE_RC}" != "0" || "${SUCCESSOR_RC}" != "0" || "${CLASSIFIER_RC}" != "0" ]]; then
  echo "HISTORICAL_REPLAY=REJECTED run_id=${RUN_ID} monitor_rc=${MONITOR_RC} px4_rc=${PX4_RC} clock_rc=${CLOCK_RC} route_rc=${ROUTE_RC} successor_rc=${SUCCESSOR_RC}" >&2
  exit 20
fi
echo "HISTORICAL_REPLAY=ACCEPTED run_id=${RUN_ID} classification=$(jq -r .classification "${ATTEMPT_RESULT}")"
