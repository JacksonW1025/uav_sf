#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
LOG_DIR="${REPO_ROOT}/docs"
LOG_FILE="${PX4_RAPTOR_UNCLIPPED_SIH_BUILD_LOG:-${LOG_DIR}/m0_raptor_unclipped_sih_build.log}"
PATCH_FILE="${REPO_ROOT}/patches/px4/raptor_unclipped.patch"

mkdir -p "${LOG_DIR}"

apply_unclipped_patch() {
  if git -C "${PX4_DIR}" apply --check "${PATCH_FILE}" >/dev/null 2>&1; then
    git -C "${PX4_DIR}" apply "${PATCH_FILE}"
    echo "Applied ${PATCH_FILE}"
  elif git -C "${PX4_DIR}" apply --reverse --check "${PATCH_FILE}" >/dev/null 2>&1; then
    echo "Patch already applied: ${PATCH_FILE}"
  else
    echo "Cannot apply or verify already-applied patch: ${PATCH_FILE}" >&2
    git -C "${PX4_DIR}" apply --check "${PATCH_FILE}"
  fi
}

{
  echo "# PX4 RAPTOR UNCLIPPED + SIH SITL build"
  date -Is
  echo "PX4_DIR=${PX4_DIR}"
  echo "PX4_SHA=$(git -C "${PX4_DIR}" rev-parse HEAD)"

  apply_unclipped_patch
  "${REPO_ROOT}/scripts/install_raptor_unclipped_sih_board.sh"
  "${REPO_ROOT}/scripts/install_m1_sih_x500.sh"
  "${REPO_ROOT}/scripts/install_fuzz1b_dds_groundtruth.sh"
  "${REPO_ROOT}/scripts/install_m2b_state_shim.sh"

  cd "${PX4_DIR}"
  HEADLESS=1 make px4_sitl_raptor_unclipped_sih

  targets_file="$(mktemp)"
  ninja -C build/px4_sitl_raptor_unclipped_sih -t targets > "${targets_file}"
  grep -E '^sihsim_quadx(:|_)' "${targets_file}" | sed -n '1,20p'
  rm -f "${targets_file}"
} | tee "${LOG_FILE}"
