#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_DIR="${PX4_BASE_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
MUTANT_DIR="${PX4_ORACLE_MUTANT_DIR:-${REPO_ROOT}/external/PX4-Autopilot-oracle-validation-mutant}"
LOCKED_COMMIT="$(python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py" --get px4_autopilot.commit)"
OBSERVABILITY_PATCH="${REPO_ROOT}/patches/px4/route_observability/route_observability_topics.patch"
MUTANT_PATCH="${REPO_ROOT}/patches/px4/oracle_validation_mutants/mc_pos_control_route_mutants.patch"

test "$(git -C "${BASE_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
test -z "$(git -C "${BASE_DIR}" status --porcelain --untracked-files=no --ignore-submodules=all)"

if [[ ! -e "${MUTANT_DIR}/.git" ]]; then
  git -C "${BASE_DIR}" worktree add --detach "${MUTANT_DIR}" "${LOCKED_COMMIT}"
  git -C "${MUTANT_DIR}" apply "${OBSERVABILITY_PATCH}"
  git -C "${MUTANT_DIR}" apply --recount "${MUTANT_PATCH}"
  sed -i -E 's/^uint8 ORB_QUEUE_LENGTH = (1|4|8|16|32)$/uint8 ORB_QUEUE_LENGTH = 4/' \
    "${MUTANT_DIR}/msg/RouteObservability.msg"
fi

test "$(git -C "${MUTANT_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
rg -q 'TEST-ONLY ORACLE VALIDATION MUTANT' \
  "${MUTANT_DIR}/src/modules/mc_pos_control/MulticopterPositionControl.cpp"
git -C "${MUTANT_DIR}" diff --check

make -C "${MUTANT_DIR}" -j"$(nproc)" px4_sitl_default \
  CMAKE_ARGS='-DCMAKE_CXX_FLAGS=-DROUTE_OBSERVABILITY_TRANSITION=1'
test -x "${MUTANT_DIR}/build/px4_sitl_default/bin/px4"
test "$(sed -n -E 's/^#define ROUTE_OBSERVABILITY_ORB_QUEUE_LENGTH ([0-9]+)$/\1/p' \
  "${MUTANT_DIR}/build/px4_sitl_default/uORB/topics/route_observability.h")" = 4

mkdir -p "${REPO_ROOT}/runs/oracle_validation/mutant_build"
python3 - "${REPO_ROOT}/runs/oracle_validation/mutant_build/provenance.json" \
  "${LOCKED_COMMIT}" "${OBSERVABILITY_PATCH}" "${MUTANT_PATCH}" "${MUTANT_DIR}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

output, commit, observation_patch, mutant_patch, mutant_dir = sys.argv[1:]
record = {
    "schema_version": "1.0",
    "sut_kind": "TEST-ONLY ORACLE VALIDATION MUTANT",
    "canonical": False,
    "px4_commit": commit,
    "observation_patch_sha256": hashlib.sha256(Path(observation_patch).read_bytes()).hexdigest(),
    "mutant_patch_sha256": hashlib.sha256(Path(mutant_patch).read_bytes()).hexdigest(),
    "mutant_worktree": mutant_dir,
    "profile": "TRANSITION",
    "uorb_queue_length": 4,
}
Path(output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf 'PX4_ORACLE_MUTANT_DIR=%s\nPX4_ORACLE_MUTANT_BUILD=%s\n' \
  "${MUTANT_DIR}" "${MUTANT_DIR}/build/px4_sitl_default/bin/px4"
