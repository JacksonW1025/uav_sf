#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
AGENT_DIR="${MICROXRCE_AGENT_DIR:-${REPO_ROOT}/external/Micro-XRCE-DDS-Agent}"
LOG_DIR="${REPO_ROOT}/docs"
SIM="${M0_SIM:-sih}"
SWITCH_DELAY="${M0_SWITCH_DELAY:-42}"
RUN_TIMEOUT="${M0_RUN_TIMEOUT:-180}"
AGENT_PORT="${AGENT_PORT:-8888}"
MAVLINK_MASTER="${MAVLINK_MASTER:-udp:127.0.0.1:14540}"

case "${SIM}" in
  sih)
    PX4_BUILD_TARGET="px4_sitl_raptor_sih"
    PX4_SIM_TARGET="sihsim_quadx"
    BUILD_DIR="${PX4_DIR}/build/px4_sitl_raptor_sih"
    RUN_ROOT="${BUILD_DIR}"
    LOG_ROOT="${RUN_ROOT}/log"
    "${REPO_ROOT}/scripts/install_raptor_sih_board.sh" >/dev/null
    ;;
  gz)
    PX4_BUILD_TARGET="px4_sitl_raptor"
    PX4_SIM_TARGET="gz_x500"
    BUILD_DIR="${PX4_DIR}/build/px4_sitl_raptor"
    RUN_ROOT="${BUILD_DIR}/rootfs"
    LOG_ROOT="${RUN_ROOT}/log"
    ;;
  *)
    echo "Unsupported M0_SIM=${SIM}; expected sih or gz" >&2
    exit 1
    ;;
esac

mkdir -p "${LOG_DIR}" "${RUN_ROOT}/raptor" "${RUN_ROOT}/etc/logging"

FULL_LOG="${LOG_DIR}/m0_px4_console.log"
SMOKE_LOG="${LOG_DIR}/m0_raptor_sih_smoke.log"
CLASSICAL_LOG="${LOG_DIR}/m0_classical_takeoff.log"
SWITCH_LOG="${LOG_DIR}/m0_switch_to_raptor.log"
ULOG_INFO_LOG="${LOG_DIR}/m0_ulog_info.log"
ULOG_SANITY_LOG="${LOG_DIR}/m0_ulog_sanity.log"

cleanup() {
  jobs -pr | xargs -r kill 2>/dev/null || true
  pkill -TERM -f 'MicroXRCEAgent|/bin/px4|gz sim|ruby.*sitl_run' 2>/dev/null || true
  sleep 1
  pkill -KILL -f 'MicroXRCEAgent|/bin/px4|gz sim|ruby.*sitl_run' 2>/dev/null || true
}
trap cleanup EXIT

set +u
source /opt/ros/jazzy/setup.bash
if [[ -f "${REPO_ROOT}/ros2_ws/install/setup.bash" ]]; then
  source "${REPO_ROOT}/ros2_ws/install/setup.bash"
fi
set -u

agent_bin="${MICROXRCE_AGENT_BIN:-}"
if [[ -z "${agent_bin}" ]] && command -v MicroXRCEAgent >/dev/null 2>&1; then
  agent_bin="$(command -v MicroXRCEAgent)"
fi
if [[ -z "${agent_bin}" ]]; then
  agent_bin="${AGENT_DIR}/build/MicroXRCEAgent"
fi
if [[ ! -x "${agent_bin}" ]]; then
  echo "MicroXRCEAgent binary not found: ${agent_bin}" >&2
  exit 1
fi

export LD_LIBRARY_PATH="${AGENT_DIR}/build:${AGENT_DIR}/build/temp_install/fastrtps-2.14/lib:${AGENT_DIR}/build/temp_install/fastcdr-2.2.0/lib:${AGENT_DIR}/build/temp_install/microxrcedds_client-2.4.3/lib:${AGENT_DIR}/build/temp_install/microcdr-2.0.1/lib:${LD_LIBRARY_PATH:-}"

cp -f "${PX4_DIR}/src/modules/mc_raptor/blob/policy.tar" "${RUN_ROOT}/raptor/policy.tar"
cat > "${RUN_ROOT}/etc/logging/logger_topics.txt" <<'TOPICS'
raptor_status 0
raptor_input 0
trajectory_setpoint 0
vehicle_local_position 0
vehicle_angular_velocity 0
vehicle_attitude 0
vehicle_status 0
actuator_motors 0
TOPICS

rm -rf "${LOG_ROOT}"
mkdir -p "${LOG_ROOT}"

cmd_file="$(mktemp)"
cat > "${cmd_file}" <<'CMDS'
sleep 6
param set NAV_DLL_ACT 0
param set COM_DISARM_LAND -1
param set IMU_GYRO_RATEMAX 250
param set COM_RC_IN_MODE 4
param set COM_RCL_EXCEPT 8
param set MC_RAPTOR_ENABLE 1
param set MC_RAPTOR_OFFB 0
param set MC_RAPTOR_INTREF 0
mc_raptor start
sleep 4
mc_raptor status
commander status
logger status
commander takeoff
sleep 25
commander status
listener vehicle_local_position 1
listener vehicle_attitude 1
sleep 40
commander status
listener vehicle_status 1
listener vehicle_local_position 1
listener vehicle_angular_velocity 1
logger status
shutdown
CMDS

agent_log="$(mktemp)"
topic_log="$(mktemp)"
switch_cmd_log="$(mktemp)"

{
  echo "# M0 PX4 console"
  date -Is
  echo "SIM=${SIM}"
  echo "PX4_BUILD_TARGET=${PX4_BUILD_TARGET}"
  echo "PX4_SIM_TARGET=${PX4_SIM_TARGET}"
  echo "PX4_SHA=$(git -C "${PX4_DIR}" rev-parse HEAD)"
  echo "MAVLINK_MASTER=${MAVLINK_MASTER}"
  echo "SWITCH_DELAY=${SWITCH_DELAY}"
  echo "RUN_ROOT=${RUN_ROOT}"
  echo "LOGGER_TOPICS=${RUN_ROOT}/etc/logging/logger_topics.txt"
  echo "POLICY=${RUN_ROOT}/raptor/policy.tar"
  ls -l "${RUN_ROOT}/raptor/policy.tar"
  echo
} > "${FULL_LOG}"

"${agent_bin}" udp4 -p "${AGENT_PORT}" >"${agent_log}" 2>&1 &
agent_pid=$!
sleep 2

if [[ "${SIM}" == "sih" ]]; then
  (
    cd "${RUN_ROOT}"
    timeout "${RUN_TIMEOUT}" env HEADLESS=1 PX4_SIM_SPEED_FACTOR="${PX4_SIM_SPEED_FACTOR:-1}" \
      PX4_SIMULATOR=sihsim PX4_SIM_MODEL="${PX4_SIM_TARGET}" ./bin/px4 . < "${cmd_file}"
  ) >> "${FULL_LOG}" 2>&1 &
else
  (
    cd "${PX4_DIR}"
    timeout "${RUN_TIMEOUT}" env HEADLESS=1 PX4_SIM_SPEED_FACTOR="${PX4_SIM_SPEED_FACTOR:-1}" \
      make "${PX4_BUILD_TARGET}" "${PX4_SIM_TARGET}" < "${cmd_file}"
  ) >> "${FULL_LOG}" 2>&1 &
fi
px4_pid=$!
px4_start_seconds=${SECONDS}

topic_found=0
topic_deadline=$((SECONDS + 70))
while (( SECONDS < topic_deadline )); do
  if ! kill -0 "${px4_pid}" 2>/dev/null; then
    break
  fi
  if timeout 5 ros2 topic list >"${topic_log}" 2>/dev/null && grep -q '^/fmu/out/' "${topic_log}"; then
    topic_found=1
    break
  fi
  sleep 2
done

{
  echo "# M0 RAPTOR+SIH smoke"
  date -Is
  echo "SIM=${SIM}"
  echo "PX4_BUILD_TARGET=${PX4_BUILD_TARGET}"
  echo "PX4_SIM_TARGET=${PX4_SIM_TARGET}"
  echo "DDS_TOPICS_FOUND=${topic_found}"
  echo
  echo "## Agent log excerpt"
  sed -n '1,80p' "${agent_log}" | cut -c1-240
  echo
  echo "## ROS 2 topics"
  if [[ -s "${topic_log}" ]]; then
    sort "${topic_log}"
  else
    timeout 5 ros2 topic list | sort || true
  fi
  echo
  echo "## PX4 relevant startup lines"
  tr '\r' '\n' < "${FULL_LOG}" \
    | grep -aE 'simulator_sih|uxrce_dds|Policy loaded|Raptor mode|External Mode|mc_raptor|Startup script|logger|ERROR|WARN' \
    | cut -c1-240 \
    | sed -n '1,160p'
} > "${SMOKE_LOG}"

elapsed_since_px4_start=$((SECONDS - px4_start_seconds))
if (( elapsed_since_px4_start < SWITCH_DELAY )); then
  sleep $((SWITCH_DELAY - elapsed_since_px4_start))
fi
{
  echo "# M0 switch to RAPTOR"
  date -Is
  echo "COMMAND=python3 scripts/m0_set_raptor_mode.py --master ${MAVLINK_MASTER} --mode-id 23"
  "${REPO_ROOT}/scripts/m0_set_raptor_mode.py" --master "${MAVLINK_MASTER}" --mode-id 23
} > "${switch_cmd_log}" 2>&1

set +e
wait "${px4_pid}"
px4_rc=$?
set -e

if [[ "${px4_rc}" -ne 0 && "${px4_rc}" -ne 124 ]]; then
  echo "PX4 exited with ${px4_rc}" >> "${FULL_LOG}"
fi

{
  echo "# M0 classical takeoff"
  date -Is
  echo "SIM=${SIM}"
  echo "COMMAND=commander takeoff"
  echo
  echo "## PX4 console excerpt"
  takeoff_line="$(grep -an -m1 'commander takeoff' "${FULL_LOG}" | cut -d: -f1 || true)"
  rapto_sleep_line="$(grep -an -m1 'sleep 40' "${FULL_LOG}" | cut -d: -f1 || true)"
  if [[ -n "${takeoff_line}" && -n "${rapto_sleep_line}" ]]; then
    start_line=$((takeoff_line > 20 ? takeoff_line - 20 : 1))
    end_line=$((rapto_sleep_line - 1))
    sed -n "${start_line},${end_line}p" "${FULL_LOG}"
  else
    tr '\r' '\n' < "${FULL_LOG}" \
      | grep -aE 'commander takeoff|Takeoff|armed|Disarmed|commander status|vehicle_local_position|vehicle_attitude|nav_state|failsafe|ERROR|WARN|INFO  \[commander\]' \
      | cut -c1-240 \
      | sed -n '1,220p'
  fi
} > "${CLASSICAL_LOG}"

latest_ulg="$(find "${LOG_ROOT}" -name '*.ulg' -type f | sort | tail -n 1 || true)"
if [[ -z "${latest_ulg}" ]]; then
  echo "No ULOG found under ${LOG_ROOT}" >&2
  exit 1
fi
cp -f "${latest_ulg}" "${LOG_DIR}/m0_run.ulg"

{
  echo "# M0 ULOG info"
  date -Is
  echo "SOURCE_ULOG=${latest_ulg}"
  echo "COPIED_ULOG=${LOG_DIR}/m0_run.ulg"
  echo
  ulog_info "${LOG_DIR}/m0_run.ulg"
  echo
  echo "## ulog_messages head"
  ulog_messages "${LOG_DIR}/m0_run.ulg" | head -n 80
} > "${ULOG_INFO_LOG}" 2>&1

"${REPO_ROOT}/scripts/m0_ulog_sanity.py" "${LOG_DIR}/m0_run.ulg" > "${ULOG_SANITY_LOG}"

{
  cat "${switch_cmd_log}"
  echo
  echo "## PX4 console excerpt after RAPTOR switch"
  switch_line="$(grep -an -m1 'Resetting Inference Executor' "${FULL_LOG}" | cut -d: -f1 || true)"
  exit_line="$(grep -an 'Exiting NOW' "${FULL_LOG}" | tail -n 1 | cut -d: -f1 || true)"
  if [[ -n "${switch_line}" && -n "${exit_line}" ]]; then
    start_line=$((switch_line > 5 ? switch_line - 5 : 1))
    sed -n "${start_line},${exit_line}p" "${FULL_LOG}"
  else
    tr '\r' '\n' < "${FULL_LOG}" \
      | grep -aE 'RAPTOR|External Mode|nav_state|commander|vehicle_status|vehicle_local_position|vehicle_angular_velocity|ERROR|WARN' \
      | cut -c1-240 \
      | tail -n 180
  fi
  echo
  echo "## ULOG switch sanity"
  grep -E 'VEHICLE_STATUS_NAV_STATES|RAPTOR_NAV_STATE_23_FIRST|ARMING_STATES_AFTER_RAPTOR|DISARMED_AFTER_RAPTOR|LOCAL_POSITION_AFTER_RAPTOR|ANGULAR_VELOCITY_AFTER_RAPTOR|ATTITUDE_QUATERNION_AFTER_RAPTOR' "${ULOG_SANITY_LOG}"
} > "${SWITCH_LOG}"

echo "M0_RUN_ULOG=${LOG_DIR}/m0_run.ulg"
echo "M0_PX4_RC=${px4_rc}"
echo "M0_DDS_TOPICS_FOUND=${topic_found}"
