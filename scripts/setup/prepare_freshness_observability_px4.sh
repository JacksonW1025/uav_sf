#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_DIR="${PX4_BASE_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
PX4_DIR="${PX4_FRESHNESS_OBSERVABILITY_DIR:-${REPO_ROOT}/external/PX4-Autopilot-freshness-observability}"
BASE_PATCH="${REPO_ROOT}/patches/px4/route_observability/route_observability_topics.patch"
FRESHNESS_PATCH="${REPO_ROOT}/patches/px4/route_observability/freshness_observability.patch"
LOCKED_COMMIT="$(python3 "${REPO_ROOT}/scripts/setup/verify_dependency_lock.py" --get px4_autopilot.commit)"
BUILD=0
PROFILE="BASELINE"

while (($#)); do
  case "$1" in
    --build) BUILD=1 ;;
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

test "$(git -C "${BASE_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"
test -z "$(git -C "${BASE_DIR}" status --porcelain)"

if [[ ! -e "${PX4_DIR}/.git" ]]; then
  git -C "${BASE_DIR}" worktree add --detach "${PX4_DIR}" "${LOCKED_COMMIT}"
fi
test "$(git -C "${PX4_DIR}" rev-parse HEAD)" = "${LOCKED_COMMIT}"

apply_or_confirm() {
  local patch="$1"
  if git -C "${PX4_DIR}" apply --check "${patch}"; then
    git -C "${PX4_DIR}" apply "${patch}"
  elif git -C "${PX4_DIR}" apply --reverse --check "${patch}"; then
    return 0
  else
    echo "patch has a partial or incompatible state: ${patch}" >&2
    exit 50
  fi
}

apply_or_confirm "${BASE_PATCH}"
apply_or_confirm "${FRESHNESS_PATCH}"
git -C "${PX4_DIR}" diff --check

if ((BUILD)); then
  CMAKE_PROFILE_ARGS=""
  if [[ "${PROFILE}" == "TRANSITION" ]]; then
    CMAKE_PROFILE_ARGS="-DCMAKE_CXX_FLAGS=-DROUTE_OBSERVABILITY_TRANSITION=1"
  fi
  make -C "${PX4_DIR}" -j"$(nproc)" px4_sitl_default CMAKE_ARGS="${CMAKE_PROFILE_ARGS}"
  test -x "${PX4_DIR}/build/px4_sitl_default/bin/px4"
  test -f "${PX4_DIR}/build/px4_sitl_default/uORB/topics/route_observability.h"
fi

echo "ROUTE_OBSERVABILITY_PROFILE=${PROFILE}"
echo "PX4_FRESHNESS_OBSERVABILITY_DIR=${PX4_DIR}"
