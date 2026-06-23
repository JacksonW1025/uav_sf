#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-${REPO_ROOT}/external/PX4-Autopilot}"

src="${REPO_ROOT}/boards/px4/sitl/raptor_sih.px4board"
dst="${PX4_DIR}/boards/px4/sitl/raptor_sih.px4board"

if [[ ! -f "${src}" ]]; then
  echo "Missing source board file: ${src}" >&2
  exit 1
fi

if [[ ! -d "${PX4_DIR}/boards/px4/sitl" ]]; then
  echo "Missing PX4 SITL board directory: ${PX4_DIR}/boards/px4/sitl" >&2
  exit 1
fi

install -m 0644 "${src}" "${dst}"
echo "Installed ${dst}"
