#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
PATCH_FILE="${REPO_ROOT}/patches/px4/m2b_state_shim.patch"

if [[ ! -d "${PX4_DIR}/.git" ]]; then
  echo "Missing PX4 git tree: ${PX4_DIR}" >&2
  exit 1
fi

if [[ ! -f "${PATCH_FILE}" ]]; then
  echo "Missing patch file: ${PATCH_FILE}" >&2
  exit 1
fi

if git -C "${PX4_DIR}" apply --reverse --check "${PATCH_FILE}" >/dev/null 2>&1; then
  echo "M2b state shim already installed in ${PX4_DIR}"
  exit 0
fi

if ! git -C "${PX4_DIR}" apply --check "${PATCH_FILE}" >/dev/null 2>&1; then
  echo "Cannot apply ${PATCH_FILE}; check PX4 commit and local modifications in ${PX4_DIR}" >&2
  exit 1
fi

git -C "${PX4_DIR}" apply "${PATCH_FILE}"
echo "Installed M2b state shim into ${PX4_DIR}"
