#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${REPO_ROOT}/data/processed/environment"
mkdir -p "${OUTPUT_DIR}"

{
  echo "# dpkg package snapshot from the Family A experiment container"
  echo "# architecture=$(dpkg --print-architecture)"
  dpkg-query -W -f='${binary:Package}\t${Version}\n' | LC_ALL=C sort
} > "${OUTPUT_DIR}/package_versions.txt"

{
  echo "# Python package snapshot from the Family A experiment container"
  python3 -m pip list --format=freeze | LC_ALL=C sort
} > "${OUTPUT_DIR}/python_packages.txt"

{
  echo "architecture=$(uname -m)"
  echo "os_release=$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '\"')"
  echo "compiler=$(gcc --version | head -1)"
  echo "cxx_compiler=$(g++ --version | head -1)"
  echo "cmake=$(cmake --version | head -1)"
  echo "python=$(python3 --version)"
  echo "ros_distro=${ROS_DISTRO:-unset}"
  echo "gazebo=$(gz sim --versions 2>/dev/null | head -1 || true)"
  echo "micro_xrce_dds_agent=$(git -C "${REPO_ROOT}/external/Micro-XRCE-DDS-Agent" describe --tags --always)"
} > "${OUTPUT_DIR}/toolchain_versions.txt"

echo "Environment snapshots written to ${OUTPUT_DIR}"
