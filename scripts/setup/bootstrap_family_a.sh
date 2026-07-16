#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/runs/setup"
UPDATE_LOCK=0
VALIDATE_ONLY=0
INSIDE="${UAV_SF_BOOTSTRAP_INSIDE:-0}"

while (($#)); do
  case "$1" in
    --update-lock) UPDATE_LOCK=1; shift ;;
    --validate-only) VALIDATE_ONLY=1; shift ;;
    --inside) INSIDE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py"
if ((VALIDATE_ONLY)); then
  bash -n "${REPO_ROOT}"/scripts/setup/*.sh
  echo "Family A bootstrap contract validated"
  exit 0
fi

if [[ "${INSIDE}" != "1" ]]; then
  "${REPO_ROOT}/docker/build.sh"
  args=(--inside)
  if ((UPDATE_LOCK)); then args+=(--update-lock); fi
  UAV_SF_BOOTSTRAP_INSIDE=1 "${REPO_ROOT}/docker/run.sh" \
    "${REPO_ROOT}/scripts/setup/bootstrap_family_a.sh" "${args[@]}"
  exit $?
fi

set +u
source /opt/ros/jazzy/setup.bash
set -u
mkdir -p "${LOG_DIR}"
update_arg=()
if ((UPDATE_LOCK)); then update_arg=(--update-lock); fi

{
  echo "# Family A bootstrap"
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  "${REPO_ROOT}/scripts/setup/clone_px4.sh" --profile family_a "${update_arg[@]}"
  "${REPO_ROOT}/scripts/setup/prepare_observability_px4.sh"
  "${REPO_ROOT}/scripts/setup/build_microxrce_agent.sh" "${update_arg[@]}"

  sudo rosdep install --from-paths "${REPO_ROOT}/ros2_ws/src" --ignore-src -r -y --rosdistro jazzy
  "${REPO_ROOT}/scripts/setup/setup_ros2_ws.sh" "${update_arg[@]}"

  python3 "${REPO_ROOT}/ros2_ws/src/px4_ros2_interface_lib/scripts/check-message-compatibility.py" \
    "${REPO_ROOT}/ros2_ws/src/px4_msgs" "${REPO_ROOT}/external/PX4-Autopilot"

  px4_observability_dir="${REPO_ROOT}/external/PX4-Autopilot-route-observability"
  cmake --build "${px4_observability_dir}/build/px4_sitl_default" --parallel "$(nproc)" 2>/dev/null || \
    make -C "${px4_observability_dir}" -j"$(nproc)" px4_sitl_default

  test -x "${px4_observability_dir}/build/px4_sitl_default/bin/px4"
  required_binaries=(
    example_mode_goto
    example_mode_with_executor
    example_executor_with_multiple_modes
    example_mode_rtl
  )
  for binary in "${required_binaries[@]}"; do
    if ! find "${REPO_ROOT}/ros2_ws/install" -type f -name "${binary}" -perm -111 -print -quit | grep -q .; then
      echo "missing official example binary: ${binary}" >&2
      exit 40
    fi
  done
  echo "FAMILY_A_BOOTSTRAP=PASS"
} | tee "${LOG_DIR}/family_a_bootstrap.log"
