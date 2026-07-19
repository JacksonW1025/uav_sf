#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="${1:-}"
if [[ ! "${RUN_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "usage: $0 RUN_ID" >&2
  exit 2
fi

set +u
# shellcheck disable=SC1090
source "${ROS_DISTRO_SETUP:-/opt/ros/humble/setup.bash}"
# shellcheck disable=SC1090
source "${ROS_WORKSPACE_SETUP:-${REPO_ROOT}/ros2_ws_humble_live/install/setup.bash}"
set -u

PX4_DIR="${SUCCESSOR_PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-control}"
EXECUTABLE="${SUCCESSOR_CURRENT_REPLAY_BIN:-${REPO_ROOT}/ros2_ws_humble_live/install/route_transition_external_mode/lib/route_transition_external_mode/issue162_replay}"
LIBRARY="${SUCCESSOR_LIBRARY_BIN:-${REPO_ROOT}/ros2_ws_humble_live/install/px4_ros2_cpp/lib/libpx4_ros2_cpp.so}"
BUILD_PROVENANCE="${SUCCESSOR_CURRENT_BUILD_PROVENANCE:-${REPO_ROOT}/experiments/motivation/successor/current_replay_build_provenance.json}"
RAW_DIR="${SUCCESSOR_RUN_ROOT:-${REPO_ROOT}/runs/motivation/successor/current}/${RUN_ID}/raw"
PROCESSED_DIR="${SUCCESSOR_PROCESSED_ROOT:-${REPO_ROOT}/data/processed/motivation/successor/current}/${RUN_ID}"
REPLAY_LOG="${RAW_DIR}/current_replay.log"
ATTEMPT_RESULT="${PROCESSED_DIR}/attempt_result.json"

[[ -x "${EXECUTABLE}" ]] || { echo "Issue #162 replay executable is unavailable" >&2; exit 4; }
[[ -f "${LIBRARY}" ]] || { echo "px4_ros2_cpp library is unavailable" >&2; exit 4; }
[[ -f "${BUILD_PROVENANCE}" ]] || { echo "current replay build provenance is unavailable" >&2; exit 4; }
[[ "$(git -C "${PX4_DIR}" rev-parse HEAD)" == "4ae21a5e569d3d89c2f6366688cbacb3e93437c9" ]] \
  || { echo "PX4 revision differs from current replay lock" >&2; exit 5; }
[[ "$(git -C "${REPO_ROOT}/ros2_ws/src/px4_ros2_interface_lib" rev-parse HEAD)" == "c3e410f035806e8c56246708432ded09c976434b" ]] \
  || { echo "library source revision differs from current replay lock" >&2; exit 5; }
[[ "$(sha256sum "${PX4_DIR}/build/px4_sitl_default/bin/px4" | awk '{print $1}')" == "931320a07585dabf36ca9c8ba994756b93ee7d154cd9c8930b2171548d978993" ]] \
  || { echo "PX4 binary differs from current replay lock" >&2; exit 5; }
[[ "$(sha256sum "${LIBRARY}" | awk '{print $1}')" == "dddfa0698c27617ce5a368dc7d0d5272bc510f3cb780c5ef3f48c77d098380e6" ]] \
  || { echo "library binary differs from current replay lock" >&2; exit 5; }
[[ "$(sha256sum "${EXECUTABLE}" | awk '{print $1}')" == "$(jq -r .adapter_binary_sha256 "${BUILD_PROVENANCE}")" ]] \
  || { echo "replay executable differs from build provenance" >&2; exit 5; }
[[ "$(sha256sum "${REPO_ROOT}/scripts/adapters/external_mode_adapter/src/issue162_replay.cpp" | awk '{print $1}')" == "$(jq -r .adapter_source_sha256 "${BUILD_PROVENANCE}")" ]] \
  || { echo "replay source differs from build provenance" >&2; exit 5; }
[[ "$(sha256sum "${REPO_ROOT}/experiments/probes/p5/p5_v6_differential_gate.json" | awk '{print $1}')" == "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc" ]] \
  || { echo "protected P5 v6 Gate changed" >&2; exit 5; }
[[ "$(sha256sum "${REPO_ROOT}/experiments/probes/p5/campaign_seeded_v6_manifest.json" | awk '{print $1}')" == "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518" ]] \
  || { echo "protected P5 v6 manifest changed" >&2; exit 5; }
if ! git -C "${REPO_ROOT}" diff --quiet || ! git -C "${REPO_ROOT}" diff --cached --quiet; then
  echo "tracked repository changes must be committed before a formal current replay" >&2
  exit 6
fi
if [[ -e "${RAW_DIR}" || -e "${PROCESSED_DIR}" ]]; then
  echo "run_id already has an artifact directory: ${RUN_ID}" >&2
  exit 3
fi
mkdir -p "${RAW_DIR}" "${PROCESSED_DIR}"

set +e
timeout 15s "${EXECUTABLE}" >"${REPLAY_LOG}" 2>&1
REPLAY_RC=$?
set -e

python3 "${REPO_ROOT}/scripts/analysis/classify_successor_current_replay.py" \
  --run-id "${RUN_ID}" --replay-log "${REPLAY_LOG}" \
  --replay-exit-code "${REPLAY_RC}" --executable "${EXECUTABLE}" \
  --library "${LIBRARY}" --px4-dir "${PX4_DIR}" \
  --build-provenance "${BUILD_PROVENANCE}" --output "${ATTEMPT_RESULT}"
