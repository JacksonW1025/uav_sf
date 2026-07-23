#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK="${REPO_ROOT}/containers/family_a_fuzzer_v0/source-commits.lock.yaml"
WORKSPACE=/opt/family_a/workspace
SOURCE="${WORKSPACE}/src"
ROS_WS="${WORKSPACE}/ros"
DDS_BUILD="${WORKSPACE}/dds"
INVENTORY=/opt/family_a/build-inventory
PARALLEL="${FAMILY_A_BUILD_JOBS:-$(nproc)}"

retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if "$@"; then
      return 0
    fi
    if [[ "${attempt}" == 5 ]]; then
      return 1
    fi
    sleep "$((attempt * 2))"
  done
}

lock_value() {
  python3 - "${LOCK}" "$1" <<'PY'
import sys
from pathlib import Path
import yaml
value = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}

checkout_exact() {
  local name="$1"
  local destination="$2"
  local repository commit
  repository="$(lock_value "sources.${name}.repository")"
  commit="$(lock_value "sources.${name}.commit")"
  git init -q "${destination}"
  git -C "${destination}" remote add origin "${repository}"
  git -C "${destination}" config http.version HTTP/1.1
  retry git -C "${destination}" fetch -q --depth=1 origin "${commit}"
  git -C "${destination}" checkout -q --detach FETCH_HEAD
  test "$(git -C "${destination}" rev-parse HEAD)" = "${commit}"
}

mkdir -p "${SOURCE}" "${ROS_WS}/src" "${DDS_BUILD}" "${INVENTORY}"

checkout_exact PX4 "${SOURCE}/PX4-Autopilot"
retry git -C "${SOURCE}/PX4-Autopilot" submodule update --init --depth=1 --recursive \
  Tools/simulation/gz \
  src/lib/cdrstream/cyclonedds \
  src/lib/cdrstream/rosidl \
  src/lib/events/libevents \
  src/lib/heatshrink/heatshrink \
  src/modules/mavlink/mavlink \
  src/modules/simulation/gz_plugins/optical_flow/PX4-OpticalFlow \
  src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client \
  src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client-v3
git -C "${SOURCE}/PX4-Autopilot" apply \
  "${REPO_ROOT}/patches/px4/route_observability/route_observability_topics.patch"
git -C "${SOURCE}/PX4-Autopilot" apply \
  "${REPO_ROOT}/patches/px4/route_observability/freshness_observability.patch"
git -C "${SOURCE}/PX4-Autopilot" diff --check
make -C "${SOURCE}/PX4-Autopilot" -j"${PARALLEL}" px4_sitl_default
test -x "${SOURCE}/PX4-Autopilot/build/px4_sitl_default/bin/px4"
test -f "${SOURCE}/PX4-Autopilot/build/px4_sitl_default/uORB/topics/route_observability.h"

checkout_exact px4_msgs "${ROS_WS}/src/px4_msgs"
checkout_exact px4_ros2_interface_lib "${ROS_WS}/src/px4_ros2_interface_lib"
git -C "${ROS_WS}/src/px4_ros2_interface_lib" apply \
  "${REPO_ROOT}/patches/px4_ros2_interface/health_reply_gate.patch"
cp -a "${REPO_ROOT}/scripts/adapters/external_mode_adapter" \
  "${ROS_WS}/src/route_transition_external_mode"

set +u
source /opt/ros/jazzy/setup.bash
set -u
colcon --log-base "${ROS_WS}/log" build \
  --base-paths "${ROS_WS}/src" \
  --build-base "${ROS_WS}/build" \
  --install-base "${ROS_WS}/install" \
  --merge-install \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  --parallel-workers "${PARALLEL}"
test -x "${ROS_WS}/install/lib/route_transition_external_mode/c1_concurrency_probe"

checkout_exact Micro_XRCE_DDS_Agent "${SOURCE}/Micro-XRCE-DDS-Agent"
cmake -S "${SOURCE}/Micro-XRCE-DDS-Agent" -B "${DDS_BUILD}" \
  -DUAGENT_SUPERBUILD=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "${DDS_BUILD}" --parallel "${PARALLEL}"
test -x "${DDS_BUILD}/MicroXRCEAgent"

git -C "${SOURCE}/PX4-Autopilot" submodule status --recursive \
  > "${INVENTORY}/px4-submodules.txt"
dpkg-query -W -f='${binary:Package}\t${Version}\n' | LC_ALL=C sort \
  > "${INVENTORY}/dpkg-packages.tsv"
python3 -m pip list --format=json \
  > "${INVENTORY}/python-packages.json"
colcon list --base-paths "${ROS_WS}/src" \
  > "${INVENTORY}/colcon-packages.tsv"
python3 - "${INVENTORY}/px4-build-provenance.json" <<'PY'
import json
import os
import pathlib
value = {
    "schema_version": "1.0",
    "repository_implementation_commit": os.environ["FAMILY_A_IMPLEMENTATION_COMMIT"],
    "px4_commit": "4ae21a5e569d3d89c2f6366688cbacb3e93437c9",
    "route_observability_patch": "735555764c175ebd0a318723d4e76b8898965c4728ee4cab9b05b6c34d5e8b7c",
    "freshness_observability_patch": "7cc9aa3a99ba34ebd75094e291a357e679ce7176d112687ed75d1bf4b2339141",
    "profile": "BASELINE",
    "uorb_queue_length": 4,
    "build_target": "px4_sitl_default",
    "build_type": "default_PX4_RelWithDebInfo",
}
pathlib.Path(__import__("sys").argv[1]).write_text(
    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

printf 'FAMILY_A_BUILD_ALL=PASS\n'
