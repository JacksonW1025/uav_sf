#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
AGENT_DIR="${MICROXRCE_AGENT_DIR:-${REPO_ROOT}/external/Micro-XRCE-DDS-Agent}"
LOG_DIR="${REPO_ROOT}/docs"
LOG_FILE="${LOG_DIR}/phase1_dds_topics.log"
AGENT_PORT="${AGENT_PORT:-8888}"
WAIT_SECONDS="${DDS_WAIT_SECONDS:-150}"

mkdir -p "${LOG_DIR}"
set +u
source /opt/ros/jazzy/setup.bash
if [[ -f "${REPO_ROOT}/ros2_ws/install/setup.bash" ]]; then
  source "${REPO_ROOT}/ros2_ws/install/setup.bash"
fi
set -u

cleanup() {
  jobs -pr | xargs -r kill || true
  pkill -TERM -f 'MicroXRCEAgent|/bin/px4|gz sim|ruby.*sitl_run' || true
  sleep 1
  pkill -KILL -f 'MicroXRCEAgent|/bin/px4|gz sim|ruby.*sitl_run' || true
}
trap cleanup EXIT

{
  echo "# DDS smoke"
  date -Is
  echo "PX4_SHA=$(git -C "${PX4_DIR}" rev-parse HEAD)"
  echo "AGENT_PORT=${AGENT_PORT}"
  echo "WAIT_SECONDS=${WAIT_SECONDS}"

  agent_bin="${MICROXRCE_AGENT_BIN:-}"
  if [[ -z "${agent_bin}" ]] && command -v MicroXRCEAgent >/dev/null 2>&1; then
    agent_bin="$(command -v MicroXRCEAgent)"
  fi
  if [[ -z "${agent_bin}" ]]; then
    agent_bin="${AGENT_DIR}/build/MicroXRCEAgent"
  fi
  if [[ ! -x "${agent_bin}" ]]; then
    echo "MicroXRCEAgent binary not found: ${agent_bin}" >&2
    echo "Run ./scripts/build_microxrce_agent.sh first." >&2
    exit 1
  fi
  echo "AGENT_BIN=${agent_bin}"

  export LD_LIBRARY_PATH="${AGENT_DIR}/build:${AGENT_DIR}/build/temp_install/fastrtps-2.14/lib:${AGENT_DIR}/build/temp_install/fastcdr-2.2.0/lib:${AGENT_DIR}/build/temp_install/microxrcedds_client-2.4.3/lib:${AGENT_DIR}/build/temp_install/microcdr-2.0.1/lib:${LD_LIBRARY_PATH:-}"

  policy_src="${PX4_DIR}/src/modules/mc_raptor/blob/policy.tar"
  policy_dst="${PX4_DIR}/build/px4_sitl_raptor/rootfs/raptor/policy.tar"
  if [[ -s "${policy_src}" ]]; then
    mkdir -p "$(dirname "${policy_dst}")"
    cp "${policy_src}" "${policy_dst}"
    ls -l "${policy_dst}"
  fi

  agent_log="$(mktemp)"
  px4_log="$(mktemp)"

  "${agent_bin}" udp4 -p "${AGENT_PORT}" >"${agent_log}" 2>&1 &
  agent_pid=$!
  sleep 2

  cd "${PX4_DIR}"
  HEADLESS=1 PX4_SIM_SPEED_FACTOR="${PX4_SIM_SPEED_FACTOR:-1}" make px4_sitl_raptor gz_x500 >"${px4_log}" 2>&1 &
  px4_pid=$!

  found=0
  deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if ! kill -0 "${agent_pid}" 2>/dev/null; then
      echo "MicroXRCEAgent exited before topics appeared"
      break
    fi
    if ! kill -0 "${px4_pid}" 2>/dev/null; then
      echo "PX4 exited before topics appeared"
      break
    fi
    if timeout 5 ros2 topic list | grep -q '^/fmu/out/'; then
      found=1
      break
    fi
    sleep 2
  done

  echo
  echo "## Agent log excerpt"
  sed -n '1,60p' "${agent_log}" | cut -c1-240
  echo
  echo "## PX4 relevant log lines"
  tr '\r' '\n' <"${px4_log}" \
    | grep -aE 'uxrce_dds|Raptor mode|Gazebo simulator|Startup script returned|Policy loaded|Policy checkpoint' \
    | cut -c1-240 \
    | head -n 80 || true
  echo
  echo "## ROS 2 topics"
  timeout 5 ros2 topic list | sort
  echo "DDS_TOPICS_FOUND=${found}"
  if [[ "${found}" -ne 1 ]]; then
    exit 1
  fi

  kill "${px4_pid}" "${agent_pid}" || true
  wait "${px4_pid}" "${agent_pid}" || true
} | tee "${LOG_FILE}"
