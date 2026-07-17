#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_DIR="${PX4_BASE_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
PATCH="${REPO_ROOT}/patches/px4/route_observability/route_observability_topics.patch"
LOCKED_COMMIT="$(python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py" --get px4_autopilot.commit)"
PROFILE=""
QUEUE_LENGTH=""
BUILD=1

while (($#)); do
  case "$1" in
    --profile) shift; PROFILE="${1:-}" ;;
    --queue-length) shift; QUEUE_LENGTH="${1:-}" ;;
    --no-build) BUILD=0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ ! "${PROFILE}" =~ ^(BASELINE|TRANSITION)$ ]]; then
  echo "profile must be BASELINE or TRANSITION" >&2
  exit 2
fi
if [[ ! "${QUEUE_LENGTH}" =~ ^(1|4|8|16|32)$ ]]; then
  echo "queue length must be one of 1, 4, 8, 16, 32" >&2
  exit 2
fi

profile_key="$(printf '%s' "${PROFILE}" | tr '[:upper:]' '[:lower:]')"
PX4_DIR="${PX4_OBSERVABILITY_DIR:-${REPO_ROOT}/external/PX4-Autopilot-route-observability-q${QUEUE_LENGTH}-${profile_key}}"
PROVENANCE_DIR="${REPO_ROOT}/runs/phase_a2/build_profiles/q${QUEUE_LENGTH}-${profile_key}"

test "$(git -C "${BASE_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
test -z "$(git -C "${BASE_DIR}" status --porcelain --untracked-files=no --ignore-submodules=all)"

if [[ ! -e "${PX4_DIR}/.git" ]]; then
  git -C "${BASE_DIR}" worktree add --detach "${PX4_DIR}" "${LOCKED_COMMIT}"
  git -C "${PX4_DIR}" apply "${PATCH}"
  sed -i -E "s/^uint8 ORB_QUEUE_LENGTH = (1|4|8|16|32)$/uint8 ORB_QUEUE_LENGTH = ${QUEUE_LENGTH}/" \
    "${PX4_DIR}/msg/RouteObservability.msg"
fi

test "$(git -C "${PX4_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
test "$(sed -n -E 's/^uint8 ORB_QUEUE_LENGTH = ([0-9]+)$/\1/p' "${PX4_DIR}/msg/RouteObservability.msg")" = "${QUEUE_LENGTH}"
git -C "${PX4_DIR}" diff --check

if ((BUILD)); then
  CMAKE_PROFILE_ARGS=""
  if [[ "${PROFILE}" == "TRANSITION" ]]; then
    CMAKE_PROFILE_ARGS="-DCMAKE_CXX_FLAGS=-DROUTE_OBSERVABILITY_TRANSITION=1"
  fi
  make -C "${PX4_DIR}" -j"$(nproc)" px4_sitl_default CMAKE_ARGS="${CMAKE_PROFILE_ARGS}"
  test -x "${PX4_DIR}/build/px4_sitl_default/bin/px4"
  generated_queue="$(sed -n -E 's/^#define ROUTE_OBSERVABILITY_ORB_QUEUE_LENGTH ([0-9]+)$/\1/p' \
    "${PX4_DIR}/build/px4_sitl_default/uORB/topics/route_observability.h")"
  test "${generated_queue}" = "${QUEUE_LENGTH}"
fi

mkdir -p "${PROVENANCE_DIR}"
python3 -c '
import hashlib, json, pathlib, sys
output, patch, px4_dir, commit, profile, queue, built = sys.argv[1:]
patch_path = pathlib.Path(patch)
record = {
    "schema_version": "1.0",
    "px4_commit": commit,
    "profile": profile,
    "uorb_queue_length": int(queue),
    "patch_sha256": hashlib.sha256(patch_path.read_bytes()).hexdigest(),
    "px4_worktree": px4_dir,
    "build_requested": built == "1",
}
pathlib.Path(output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
' "${PROVENANCE_DIR}/build_provenance.json" "${PATCH}" "${PX4_DIR}" "${LOCKED_COMMIT}" "${PROFILE}" "${QUEUE_LENGTH}" "${BUILD}"

printf 'ROUTE_OBSERVABILITY_PROFILE=%s\nORB_QUEUE_LENGTH=%s\nPX4_OBSERVABILITY_DIR=%s\nBUILD_PROVENANCE=%s\n' \
  "${PROFILE}" "${QUEUE_LENGTH}" "${PX4_DIR}" "${PROVENANCE_DIR}/build_provenance.json"
