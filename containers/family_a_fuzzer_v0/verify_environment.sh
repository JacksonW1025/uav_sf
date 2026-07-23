#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_TIME=0
if [[ "${1:-}" == "--build-time" ]]; then
  BUILD_TIME=1
fi

set +u
source /opt/ros/jazzy/setup.bash
source /opt/family_a/workspace/ros/install/setup.bash
set -u

"${SCRIPT_DIR}/verify_no_host_ros_leakage.sh"
python3 "${REPO_ROOT}/scripts/fuzzer_v0/family_a/environment_contract.py" \
  verify --repository "${REPO_ROOT}" --build-time "${BUILD_TIME}"
