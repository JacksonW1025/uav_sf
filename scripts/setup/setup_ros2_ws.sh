#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WS_DIR="${ROS2_WS_DIR:-${REPO_ROOT}/ros2_ws}"
PX4_MSGS_REPO="${PX4_MSGS_REPO:-https://github.com/PX4/px4_msgs.git}"
PX4_MSGS_REF="${PX4_MSGS_REF:-main}"
LOG_DIR="${REPO_ROOT}/runs/setup"

mkdir -p "${LOG_DIR}" "${WS_DIR}/src"

git_retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if git -c http.version=HTTP/1.1 "$@"; then
      return 0
    fi
    echo "git $* failed on attempt ${attempt}, retrying..." >&2
    sleep $((attempt * 5))
  done
  git -c http.version=HTTP/1.1 "$@"
}

set +u
source /opt/ros/jazzy/setup.bash
set -u

{
  echo "# ROS 2 workspace setup"
  date -Is
  echo "ROS_DISTRO=${ROS_DISTRO:-}"
  echo "WS_DIR=${WS_DIR}"
  echo "PX4_MSGS_REF=${PX4_MSGS_REF}"

  if [[ ! -d "${WS_DIR}/src/px4_msgs/.git" ]]; then
    git_retry clone "${PX4_MSGS_REPO}" "${WS_DIR}/src/px4_msgs"
  fi

  git -C "${WS_DIR}/src/px4_msgs" config http.version HTTP/1.1
  git_retry -C "${WS_DIR}/src/px4_msgs" fetch --tags origin
  git -C "${WS_DIR}/src/px4_msgs" checkout "${PX4_MSGS_REF}"

  colcon --log-base "${WS_DIR}/log" build \
    --base-paths "${WS_DIR}/src" \
    --build-base "${WS_DIR}/build" \
    --install-base "${WS_DIR}/install"

  git -C "${WS_DIR}/src/px4_msgs" rev-parse HEAD | tee "${LOG_DIR}/px4_msgs_commit.txt"
} | tee "${LOG_DIR}/ros2_ws_build.log"
