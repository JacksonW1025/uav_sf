#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_DIR="${PX4_BASE_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
PATCH="${REPO_ROOT}/patches/px4/route_observability/route_observability_topics.patch"
LOCKED_COMMIT="$(python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py" --get px4_autopilot.commit)"
PROFILE="${ROUTE_OBSERVABILITY_PROFILE:-TRANSITION}"
BUILD=1

while (($#)); do
  case "$1" in
    --no-build) BUILD=0 ;;
    --profile)
      shift
      PROFILE="${1:-}"
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
if [[ ! "${PROFILE}" =~ ^(BASELINE|TRANSITION)$ ]]; then
  echo "profile must be BASELINE or TRANSITION" >&2
  exit 2
fi

TEMP_ROOT="$(mktemp -d "${REPO_ROOT}/external/.route-observability-rebuild.XXXXXX")"
WORKTREE="${TEMP_ROOT}/PX4-Autopilot"
cleanup() {
  set +e
  git -C "${BASE_DIR}" worktree remove --force "${WORKTREE}" >/dev/null 2>&1
  rmdir "${TEMP_ROOT}" >/dev/null 2>&1
}
trap cleanup EXIT

test "$(git -C "${BASE_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
# The source checkout may have independently managed/ignored submodule worktrees.
# Only superproject tracked changes can affect the detached worktree's base tree.
test -z "$(git -C "${BASE_DIR}" status --porcelain --untracked-files=no --ignore-submodules=all)"
git -C "${BASE_DIR}" worktree add --detach "${WORKTREE}" "${LOCKED_COMMIT}"
test ! -e "${WORKTREE}/msg/RouteObservability.msg"
git -C "${WORKTREE}" apply "${PATCH}"
test -f "${WORKTREE}/msg/RouteObservability.msg"
git -C "${WORKTREE}" diff --check
python3 "${REPO_ROOT}/scripts/setup/check_px4_observability_patch.py" --px4-dir "${WORKTREE}"

if ((BUILD)); then
  CMAKE_PROFILE_ARGS=""
  if [[ "${PROFILE}" == "TRANSITION" ]]; then
    CMAKE_PROFILE_ARGS="-DCMAKE_CXX_FLAGS=-DROUTE_OBSERVABILITY_TRANSITION=1"
  fi
  make -C "${WORKTREE}" -j"$(nproc)" px4_sitl_default CMAKE_ARGS="${CMAKE_PROFILE_ARGS}"
  test -x "${WORKTREE}/build/px4_sitl_default/bin/px4"
  test -f "${WORKTREE}/build/px4_sitl_default/uORB/topics/route_observability.h"
fi

printf 'REBUILD_STATUS=PASS\nPROFILE=%s\nLOCKED_COMMIT=%s\n' "${PROFILE}" "${LOCKED_COMMIT}"
