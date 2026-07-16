#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=dependency_lock_lib.sh
source "${REPO_ROOT}/scripts/setup/dependency_lock_lib.sh"

WS_DIR="${ROS2_WS_DIR:-${REPO_ROOT}/ros2_ws}"
LOG_DIR="${REPO_ROOT}/runs/setup"
UPDATE_LOCK=0
SKIP_BUILD=0
while (($#)); do
  case "$1" in
    --update-lock) UPDATE_LOCK=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if ((UPDATE_LOCK)); then
  python3 "${LOCK_HELPER}" --lock "${DEPENDENCY_LOCK_FILE}" \
    --update-lock px4_msgs --update-lock px4_ros2_interface_lib
fi
lock_verify
mkdir -p "${LOG_DIR}" "${WS_DIR}/src"

ROS_DISTRO_LOCKED="$(lock_get container.ros_distro)"
ROS_SETUP="/opt/ros/${ROS_DISTRO_LOCKED}/setup.bash"
if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "missing locked ROS installation: ${ROS_SETUP}" >&2
  exit 30
fi
set +u
source "${ROS_SETUP}"
set -u

{
  echo "# ROS 2 locked workspace"
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  echo "ROS_DISTRO=${ROS_DISTRO:-}"
  checkout_locked_repository px4_msgs "${WS_DIR}/src/px4_msgs"
  checkout_locked_repository px4_ros2_interface_lib "${WS_DIR}/src/px4_ros2_interface_lib"

  if ((SKIP_BUILD == 0)); then
    colcon --log-base "${WS_DIR}/log" build \
      --base-paths "${WS_DIR}/src" \
      --build-base "${WS_DIR}/build" \
      --install-base "${WS_DIR}/install" \
      --cmake-args -DBUILD_TESTING=ON
  fi

  verify_clean_repository "${WS_DIR}/src/px4_msgs"
  verify_clean_repository "${WS_DIR}/src/px4_ros2_interface_lib"
  log_repository_identity PX4_MSGS "${WS_DIR}/src/px4_msgs"
  log_repository_identity PX4_ROS2_INTERFACE_LIB "${WS_DIR}/src/px4_ros2_interface_lib"
} | tee "${LOG_DIR}/ros2_ws_build.log"
