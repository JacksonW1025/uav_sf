#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="${MICROXRCE_AGENT_SOURCE_DIR:-${REPO_ROOT}/external/Micro-XRCE-DDS-Agent}"
BUILD_DIR="${FRESHNESS_AGENT_BUILD:-${REPO_ROOT}/runs/freshness_agent_build}"
LOCKED_COMMIT="$(python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py" --get micro_xrce_dds_agent.commit)"

test "$(git -C "${SOURCE_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
test -z "$(git -C "${SOURCE_DIR}" status --porcelain)"

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}" \
  -DUAGENT_SUPERBUILD=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "${BUILD_DIR}" -j"$(nproc)"

test -x "${BUILD_DIR}/MicroXRCEAgent"
LD_LIBRARY_PATH="${BUILD_DIR}:${BUILD_DIR}/temp_install/fastrtps-2.14/lib:${BUILD_DIR}/temp_install/fastcdr-2.2.0/lib:${BUILD_DIR}/temp_install/microxrcedds_client-2.4.3/lib" \
  "${BUILD_DIR}/MicroXRCEAgent" --help >/dev/null 2>&1 || test "$?" = 1

echo "MICROXRCE_AGENT_COMMIT=${LOCKED_COMMIT}"
echo "FRESHNESS_AGENT_BUILD=${BUILD_DIR}"
sha256sum "${BUILD_DIR}/MicroXRCEAgent" "${BUILD_DIR}/libmicroxrcedds_agent.so"
