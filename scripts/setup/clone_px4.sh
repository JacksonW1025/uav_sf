#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=dependency_lock_lib.sh
source "${REPO_ROOT}/scripts/setup/dependency_lock_lib.sh"

PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
LOG_DIR="${REPO_ROOT}/runs/setup"
PROFILE="family_a"
UPDATE_LOCK=0

while (($#)); do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --update-lock) UPDATE_LOCK=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ "${PROFILE}" != "family_a" && "${PROFILE}" != "family_b" ]]; then
  echo "profile must be family_a or family_b" >&2
  exit 2
fi
if ((UPDATE_LOCK)); then
  python3 "${LOCK_HELPER}" --lock "${DEPENDENCY_LOCK_FILE}" --update-lock px4_autopilot
fi
lock_verify
mkdir -p "${LOG_DIR}"

{
  echo "# PX4 locked checkout"
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  echo "PROFILE=${PROFILE}"
  checkout_locked_repository px4_autopilot "${PX4_DIR}"

  family_a_submodules=(
    Tools/simulation/gz
    src/lib/cdrstream/cyclonedds
    src/lib/cdrstream/rosidl
    src/lib/events/libevents
    src/lib/heatshrink/heatshrink
    src/modules/mavlink/mavlink
    src/modules/simulation/gz_plugins/optical_flow/PX4-OpticalFlow
    src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client
    src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client-v3
  )
  git -c http.version=HTTP/1.1 -C "${PX4_DIR}" submodule update --init --recursive --jobs 2 "${family_a_submodules[@]}"

  if [[ "${PROFILE}" == "family_b" ]]; then
    git -c http.version=HTTP/1.1 -C "${PX4_DIR}" submodule update --init --recursive --jobs 2 \
      src/lib/rl_tools/rl_tools src/modules/mc_raptor/blob
  fi

  verify_clean_repository "${PX4_DIR}"
  log_repository_identity PX4 "${PX4_DIR}"
} | tee "${LOG_DIR}/px4_clone.log"
