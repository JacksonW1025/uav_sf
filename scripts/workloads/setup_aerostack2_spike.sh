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
  if [[ ! -e "${path}/.git" ]]; then
    git clone "${url}" "${path}"
  fi
  git -C "${path}" fetch origin "${commit}"
  git -C "${path}" checkout --detach "${commit}"
  test "$(git -C "${path}" rev-parse HEAD)" = "${commit}"
  test -z "$(git -C "${path}" status --porcelain --untracked-files=no)"
}

mkdir -p "${WORKSPACE}/src"
ensure_checkout "${AS2_DIR}" \
  "$(lock_value source_dependencies.aerostack2.url)" \
  "$(lock_value source_dependencies.aerostack2.commit)"
ensure_checkout "${WORKSPACE}/src/as2_platform_pixhawk" \
  "$(lock_value source_dependencies.as2_platform_pixhawk.url)" \
  "$(lock_value source_dependencies.as2_platform_pixhawk.commit)"
ensure_checkout "${WORKSPACE}/src/project_px4_vision" \
  "$(lock_value source_dependencies.project_px4_vision.url)" \
  "$(lock_value source_dependencies.project_px4_vision.commit)"

test "$(git -C "${REPO_ROOT}/ros2_ws/src/px4_msgs" rev-parse HEAD)" = \
  "$(lock_value source_dependencies.px4_msgs.commit)"

set +u
source /opt/ros/humble/setup.bash
source "${REPO_ROOT}/ros2_ws_humble_live/install/setup.bash"
set -u

colcon build \
  --base-paths "${AS2_DIR}" "${WORKSPACE}/src/as2_platform_pixhawk" \
  --build-base "${WORKSPACE}/build" \
  --install-base "${WORKSPACE}/install" \
  --log-base "${WORKSPACE}/log" \
  --packages-up-to as2_platform_pixhawk \
  --cmake-args -DBUILD_TESTING=OFF

test -f "${WORKSPACE}/install/setup.bash"
printf 'AEROSTACK2_COMMIT=%s\nAEROSTACK2_INSTALL=%s\n' \
  "$(git -C "${AS2_DIR}" rev-parse HEAD)" "${WORKSPACE}/install"
