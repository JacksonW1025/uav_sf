#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK="${REPO_ROOT}/config/aerostack2_dependencies.lock.yaml"
AS2_DIR="${REPO_ROOT}/external/aerostack2"
WORKSPACE="${REPO_ROOT}/ros2_ws_aerostack2"

lock_value() {
  python3 - "${LOCK}" "$1" <<'PY'
import sys, yaml
value = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}

ensure_checkout() {
  local path="$1"
  local url="$2"
  local commit="$3"
  local compatibility_patch="${4:-}"
  if [[ ! -e "${path}/.git" ]]; then
    git clone "${url}" "${path}"
  fi
  if [[ -n "${compatibility_patch}" ]] && \
    git -C "${path}" apply --reverse --check "${compatibility_patch}" 2>/dev/null; then
    git -C "${path}" apply --reverse "${compatibility_patch}"
  fi
  git -C "${path}" fetch origin "${commit}"
  git -C "${path}" checkout --detach "${commit}"
  test "$(git -C "${path}" rev-parse HEAD)" = "${commit}"
  test -z "$(git -C "${path}" status --porcelain --untracked-files=no)"
  if [[ -n "${compatibility_patch}" ]]; then
    git -C "${path}" apply --check "${compatibility_patch}"
    git -C "${path}" apply "${compatibility_patch}"
  fi
}

mkdir -p "${WORKSPACE}/src"
ensure_checkout "${AS2_DIR}" \
  "$(lock_value source_dependencies.aerostack2.url)" \
  "$(lock_value source_dependencies.aerostack2.commit)"
ensure_checkout "${WORKSPACE}/src/as2_platform_pixhawk" \
  "$(lock_value source_dependencies.as2_platform_pixhawk.url)" \
  "$(lock_value source_dependencies.as2_platform_pixhawk.commit)" \
  "${REPO_ROOT}/patches/aerostack2/px4_msgs_current_compatibility.patch"
ensure_checkout "${WORKSPACE}/src/project_px4_vision" \
  "$(lock_value source_dependencies.project_px4_vision.url)" \
  "$(lock_value source_dependencies.project_px4_vision.commit)"
ensure_checkout "${WORKSPACE}/src/mocap4r2_msgs" \
  "$(lock_value source_dependencies.mocap4r2_msgs.url)" \
  "$(lock_value source_dependencies.mocap4r2_msgs.commit)"

test "$(git -C "${REPO_ROOT}/ros2_ws/src/px4_msgs" rev-parse HEAD)" = \
  "$(lock_value source_dependencies.px4_msgs.commit)"

set +u
source /opt/ros/humble/setup.bash
source "${REPO_ROOT}/ros2_ws_humble_live/install/setup.bash"
set -u

colcon --log-base "${WORKSPACE}/log" build \
  --base-paths \
    "${AS2_DIR}" \
    "${WORKSPACE}/src/as2_platform_pixhawk" \
    "${WORKSPACE}/src/mocap4r2_msgs" \
  --build-base "${WORKSPACE}/build" \
  --install-base "${WORKSPACE}/install" \
  --packages-up-to \
    as2_platform_pixhawk \
    as2_state_estimator \
    as2_motion_controller \
    as2_behaviors_motion \
    as2_python_api \
  --cmake-args -DBUILD_TESTING=OFF

test -f "${WORKSPACE}/install/setup.bash"
printf 'AEROSTACK2_COMMIT=%s\nAEROSTACK2_INSTALL=%s\n' \
  "$(git -C "${AS2_DIR}" rev-parse HEAD)" "${WORKSPACE}/install"
