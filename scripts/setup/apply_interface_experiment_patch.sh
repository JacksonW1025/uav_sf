#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INTERFACE_DIR="${PX4_ROS2_INTERFACE_DIR:-${REPO_ROOT}/ros2_ws/src/px4_ros2_interface_lib}"
PATCH="${REPO_ROOT}/patches/px4_ros2_interface/health_reply_gate.patch"
ACTION="${1:-apply}"

case "${ACTION}" in
  apply)
    if git -C "${INTERFACE_DIR}" apply --reverse --check "${PATCH}" 2>/dev/null; then
      echo "interface experiment patch already applied"
    elif git -C "${INTERFACE_DIR}" apply --check "${PATCH}"; then
      git -C "${INTERFACE_DIR}" apply "${PATCH}"
      echo "interface experiment patch applied"
    else
      echo "interface experiment patch cannot be applied cleanly" >&2
      exit 1
    fi
    ;;
  revert)
    if git -C "${INTERFACE_DIR}" apply --check "${PATCH}" 2>/dev/null; then
      echo "interface experiment patch already reverted"
    elif git -C "${INTERFACE_DIR}" apply --reverse --check "${PATCH}"; then
      git -C "${INTERFACE_DIR}" apply --reverse "${PATCH}"
      echo "interface experiment patch reverted"
    else
      echo "interface experiment patch cannot be reverted cleanly" >&2
      exit 1
    fi
    ;;
  *)
    echo "usage: $0 [apply|revert]" >&2
    exit 2
    ;;
esac
