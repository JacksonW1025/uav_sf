#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"
PX4_REPO="${PX4_REPO:-https://github.com/PX4/PX4-Autopilot.git}"
PX4_REF="${PX4_REF:-main}"
PX4_SUBMODULE_MODE="${PX4_SUBMODULE_MODE:-required}"
PX4_SUBMODULE_JOBS="${PX4_SUBMODULE_JOBS:-2}"
LOG_DIR="${REPO_ROOT}/runs/setup"

mkdir -p "${LOG_DIR}" "$(dirname "${PX4_DIR}")"

git_retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if git -c http.version=HTTP/1.1 "$@"; then
      return 0
    fi
    echo "git $* failed on attempt ${attempt}, retrying..." >&2
    sleep $((attempt * 5))
  done
  git -c http.version=HTTP/1.1 "$@"
}

{
  echo "# PX4 clone"
  date -Is
  echo "PX4_REPO=${PX4_REPO}"
  echo "PX4_REF=${PX4_REF}"
  echo "PX4_DIR=${PX4_DIR}"
  echo "PX4_SUBMODULE_MODE=${PX4_SUBMODULE_MODE}"

  if [[ ! -d "${PX4_DIR}/.git" ]]; then
    git_retry clone "${PX4_REPO}" "${PX4_DIR}"
  fi

  git_retry -C "${PX4_DIR}" fetch origin "${PX4_REF}"
  git -C "${PX4_DIR}" fetch --tags origin || echo "WARNING: tag fetch failed; continuing with commit pin"
  git -C "${PX4_DIR}" checkout "${PX4_REF}"
  if [[ "${PX4_SUBMODULE_MODE}" == "full" ]]; then
    git_retry -C "${PX4_DIR}" submodule update --init --recursive --jobs "${PX4_SUBMODULE_JOBS}"
  else
    required_submodules=(
      Tools/simulation/gz
      platforms/nuttx/NuttX/apps
      platforms/nuttx/NuttX/nuttx
      src/drivers/gps/devices
      src/lib/cdrstream/cyclonedds
      src/lib/cdrstream/rosidl
      src/lib/crypto/libtomcrypt
      src/lib/crypto/libtommath
      src/lib/crypto/monocypher
      src/lib/events/libevents
      src/lib/heatshrink/heatshrink
      src/lib/rl_tools/rl_tools
      src/modules/mavlink/mavlink
      src/modules/mc_raptor/blob
      src/modules/simulation/gz_plugins/optical_flow/PX4-OpticalFlow
      src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client
      src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client-v3
    )
    git_retry -C "${PX4_DIR}" submodule update --init --recursive --jobs "${PX4_SUBMODULE_JOBS}" "${required_submodules[@]}"
  fi

  required_files=(
    Tools/simulation/gz/models/x500/model.sdf
    Tools/simulation/gz/worlds/default.sdf
    platforms/nuttx/NuttX/apps/Makefile
    platforms/nuttx/NuttX/nuttx/Makefile
    src/drivers/gps/devices/src/crc.cpp
    src/lib/heatshrink/heatshrink/heatshrink_decoder.c
    src/lib/rl_tools/rl_tools/include/rl_tools/rl_tools.h
    src/modules/mavlink/mavlink/message_definitions/v1.0/common.xml
    src/modules/mc_raptor/blob/policy.tar
    src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client/CMakeLists.txt
    src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client-v3/CMakeLists.txt
  )
  for relpath in "${required_files[@]}"; do
    if [[ ! -s "${PX4_DIR}/${relpath}" ]]; then
      echo "MISSING_REQUIRED_FILE=${relpath}"
      exit 4
    fi
  done

  px4_sha="$(git -C "${PX4_DIR}" rev-parse HEAD)"
  echo "PX4_SHA=${px4_sha}"
  git -C "${PX4_DIR}" describe --tags --always --dirty || true

  if [[ -d "${PX4_DIR}/src/modules/mc_raptor" ]]; then
    echo "RAPTOR_MODULE=present"
  else
    echo "RAPTOR_MODULE=missing"
    exit 2
  fi

  policy="${PX4_DIR}/src/modules/mc_raptor/blob/policy.tar"
  if [[ -s "${policy}" ]]; then
    echo "RAPTOR_POLICY=${policy}"
    wc -c "${policy}"
    file "${policy}"
    tar -tf "${policy}" | sed -n '1,20p' || true
  else
    echo "RAPTOR_POLICY=missing_or_empty"
    ls -la "${PX4_DIR}/src/modules/mc_raptor/blob" || true
    exit 3
  fi

  printf '%s\n' "${px4_sha}" > "${LOG_DIR}/px4_commit.txt"
} | tee "${LOG_DIR}/px4_clone.log"
