#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=dependency_lock_lib.sh
source "${REPO_ROOT}/scripts/setup/dependency_lock_lib.sh"

SRC_DIR="${MICROXRCE_AGENT_DIR:-${REPO_ROOT}/external/Micro-XRCE-DDS-Agent}"
INSTALL_DIR="${MICROXRCE_AGENT_INSTALL_DIR:-${REPO_ROOT}/external/install/microxrce_agent}"
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
  python3 "${LOCK_HELPER}" --lock "${DEPENDENCY_LOCK_FILE}" --update-lock micro_xrce_dds_agent
fi
lock_verify
mkdir -p "${LOG_DIR}"

{
  echo "# Micro XRCE-DDS Agent locked build"
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  checkout_locked_repository micro_xrce_dds_agent "${SRC_DIR}"
  git -c http.version=HTTP/1.1 -C "${SRC_DIR}" submodule update --init --recursive
  if ((SKIP_BUILD == 0)); then
    cmake -S "${SRC_DIR}" -B "${SRC_DIR}/build" \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}" \
      -DUAGENT_BUILD_EXAMPLES=OFF \
      -DUAGENT_BUILD_TESTS=OFF
    cmake --build "${SRC_DIR}/build" --parallel "$(nproc)"
    cmake --install "${SRC_DIR}/build"
  fi
  verify_clean_repository "${SRC_DIR}"
  log_repository_identity MICRO_XRCE_DDS_AGENT "${SRC_DIR}"
} | tee "${LOG_DIR}/microxrce_agent_build.log"
