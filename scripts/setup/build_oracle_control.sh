#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_DIR="${PX4_BASE_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
CONTROL_DIR="${PX4_ORACLE_CONTROL_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-control}"
LOCKED_COMMIT="$(python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py" --get px4_autopilot.commit)"
OBSERVABILITY_PATCH="${REPO_ROOT}/patches/px4/route_observability/route_observability_topics.patch"

test "$(git -C "${BASE_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
test -z "$(git -C "${BASE_DIR}" status --porcelain --untracked-files=no --ignore-submodules=all)"

if [[ ! -e "${CONTROL_DIR}/.git" ]]; then
  git -C "${BASE_DIR}" worktree add --detach "${CONTROL_DIR}" "${LOCKED_COMMIT}"
  git -C "${CONTROL_DIR}" apply "${OBSERVABILITY_PATCH}"
  sed -i -E 's/^uint8 ORB_QUEUE_LENGTH = (1|4|8|16|32)$/uint8 ORB_QUEUE_LENGTH = 4/' \
    "${CONTROL_DIR}/msg/RouteObservability.msg"
fi

test "$(git -C "${CONTROL_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
if rg -q 'TEST-ONLY ORACLE VALIDATION MUTANT' \
  "${CONTROL_DIR}/src/modules/mc_pos_control/MulticopterPositionControl.cpp"; then
  echo "control worktree unexpectedly contains the test mutant" >&2
  exit 1
fi
git -C "${CONTROL_DIR}" diff --check

make -C "${CONTROL_DIR}" -j"$(nproc)" px4_sitl_default \
  CMAKE_ARGS='-DCMAKE_CXX_FLAGS=-DROUTE_OBSERVABILITY_TRANSITION=1'
test -x "${CONTROL_DIR}/build/px4_sitl_default/bin/px4"
test "$(sed -n -E 's/^#define ROUTE_OBSERVABILITY_ORB_QUEUE_LENGTH ([0-9]+)$/\1/p' \
  "${CONTROL_DIR}/build/px4_sitl_default/uORB/topics/route_observability.h")" = 4

mkdir -p "${REPO_ROOT}/runs/oracle_validation/control_build"
python3 - "${REPO_ROOT}/runs/oracle_validation/control_build/provenance.json" \
  "${LOCKED_COMMIT}" "${OBSERVABILITY_PATCH}" "${CONTROL_DIR}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

output, commit, observation_patch, control_dir = sys.argv[1:]
record = {
    "schema_version": "1.0",
    "sut_kind": "canonical locked PX4 with observation-only patch",
    "canonical": True,
    "px4_commit": commit,
    "observation_patch_sha256": hashlib.sha256(Path(observation_patch).read_bytes()).hexdigest(),
    "control_worktree": control_dir,
    "profile": "TRANSITION",
    "uorb_queue_length": 4,
}
Path(output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf 'PX4_ORACLE_CONTROL_DIR=%s\nPX4_ORACLE_CONTROL_BUILD=%s\n' \
  "${CONTROL_DIR}" "${CONTROL_DIR}/build/px4_sitl_default/bin/px4"
