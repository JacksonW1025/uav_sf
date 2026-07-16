#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
LOG_DIR="${REPO_ROOT}/runs/setup"
LOG_FILE="${PX4_MCNN_SIH_BUILD_LOG:-${LOG_DIR}/mcnn_gate1_build.log}"

mkdir -p "${LOG_DIR}"

{
  echo "# PX4 mc_nn_control + SIH SITL build"
  date -Is
  echo "PX4_DIR=${PX4_DIR}"
  echo "PX4_SHA=$(git -C "${PX4_DIR}" rev-parse HEAD)"

  "${REPO_ROOT}/family_b/scripts/install_mcnn_sih_board.sh"
  "${REPO_ROOT}/family_b/scripts/install_m1_sih_x500.sh"
  "${REPO_ROOT}/scripts/tracing/install_dds_groundtruth.sh"
  "${REPO_ROOT}/family_b/scripts/install_m2b_state_shim.sh"

  cd "${PX4_DIR}"
  HEADLESS=1 make px4_sitl_mcnn_sih

  targets_file="$(mktemp)"
  ninja -C build/px4_sitl_mcnn_sih -t targets > "${targets_file}"
  grep -E '^sihsim_quadx(:|_)' "${targets_file}" | sed -n '1,20p'
  rm -f "${targets_file}"
} | tee "${LOG_FILE}"
