#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"

airframe_src="${REPO_ROOT}/config/px4/init.d-posix/airframes/10046_sihsim_x500_v2"
airframe_dst="${PX4_DIR}/ROMFS/px4fmu_common/init.d-posix/airframes/10046_sihsim_x500_v2"
cmake_file="${PX4_DIR}/ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt"

if [[ ! -f "${airframe_src}" ]]; then
  echo "Missing source airframe: ${airframe_src}" >&2
  exit 1
fi

if [[ ! -d "${PX4_DIR}/ROMFS/px4fmu_common/init.d-posix/airframes" ]]; then
  echo "Missing PX4 airframes directory: ${PX4_DIR}/ROMFS/px4fmu_common/init.d-posix/airframes" >&2
  exit 1
fi

install -m 0755 "${airframe_src}" "${airframe_dst}"

if ! grep -qx $'\t10046_sihsim_x500_v2' "${cmake_file}"; then
  tmp_file="$(mktemp)"
  awk '
    { print }
    /^\t10045_sihsim_rover_ackermann$/ {
      print "\t10046_sihsim_x500_v2"
    }
  ' "${cmake_file}" > "${tmp_file}"
  install -m 0644 "${tmp_file}" "${cmake_file}"
  rm -f "${tmp_file}"
fi

build_airframes="${PX4_DIR}/build/px4_sitl_raptor_sih/etc/init.d-posix/airframes"
if [[ -d "${build_airframes}" ]]; then
  install -m 0755 "${airframe_src}" "${build_airframes}/10046_sihsim_x500_v2"
fi

echo "Installed SIH X500 v2 airframe into ${PX4_DIR}"
