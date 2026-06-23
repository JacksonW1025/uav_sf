#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
LOG_DIR="${REPO_ROOT}/docs"
SETUP_DEPS="${SETUP_DEPS:-0}"

mkdir -p "${LOG_DIR}"

{
  echo "# PX4 RAPTOR SITL build"
  date -Is
  echo "PX4_DIR=${PX4_DIR}"
  git -C "${PX4_DIR}" rev-parse HEAD

  if [[ "${SETUP_DEPS}" == "1" ]]; then
    sudo rm -rf /var/lib/apt/lists/*
    env -u HTTP_PROXY -u HTTPS_PROXY -u NO_PROXY \
        -u http_proxy -u https_proxy -u no_proxy \
        bash "${PX4_DIR}/Tools/setup/ubuntu.sh" --no-nuttx
  fi

  cmake --version
  ninja --version
  gz sim --version || true
  git config --global http.version HTTP/1.1

  cd "${PX4_DIR}"
  HEADLESS=1 make px4_sitl_raptor

  targets_file="$(mktemp)"
  ninja -C build/px4_sitl_raptor -t targets > "${targets_file}"

  if ! grep -q '^gz_x500:' "${targets_file}"; then
    echo "gz_x500 target missing after build; forcing CMake reconfigure"
    rm -f build/px4_sitl_raptor/CMakeCache.txt
    HEADLESS=1 make px4_sitl_raptor
    ninja -C build/px4_sitl_raptor -t targets > "${targets_file}"
  fi

  grep -E '^gz_x500(:|_)' "${targets_file}" | sed -n '1,20p'
  rm -f "${targets_file}"
} | tee "${LOG_DIR}/px4_raptor_build.log"
