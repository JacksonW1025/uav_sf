#!/usr/bin/env bash
set -euo pipefail

[[ "${FAMILY_A_FORMAL_CONTAINER:-}" == "1" ]]
[[ "${ROS_DISTRO:-}" == "jazzy" ]]

for name in AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH ROS_PACKAGE_PATH; do
  value="${!name:-}"
  if [[ "${value}" == *humble* || "${value}" == *"/home/"* || "${value}" == *"/mnt/"* ]]; then
    printf 'host ROS leakage in %s=%s\n' "${name}" "${value}" >&2
    exit 40
  fi
done

for required in \
  "${AMENT_PREFIX_PATH:-}" \
  "${CMAKE_PREFIX_PATH:-}" \
  "${COLCON_PREFIX_PATH:-}"; do
  if [[ -n "${required}" && "${required}" != *"/opt/ros/jazzy"* && "${required}" != *"/opt/family_a/workspace/ros/install"* ]]; then
    printf 'unexpected formal prefix: %s\n' "${required}" >&2
    exit 41
  fi
done

printf 'NO_HOST_ROS_LEAKAGE=PASS\n'
