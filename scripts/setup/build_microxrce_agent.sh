#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="${MICROXRCE_AGENT_DIR:-${REPO_ROOT}/external/Micro-XRCE-DDS-Agent}"
REPO_URL="${MICROXRCE_AGENT_REPO:-https://github.com/eProsima/Micro-XRCE-DDS-Agent.git}"
REF="${MICROXRCE_AGENT_REF:-v2.4.3}"
LOG_DIR="${REPO_ROOT}/runs/setup"

mkdir -p "${LOG_DIR}" "$(dirname "${SRC_DIR}")"

{
  echo "# Micro-XRCE-DDS-Agent build"
  date -Is
  echo "REPO_URL=${REPO_URL}"
  echo "REF=${REF}"
  echo "SRC_DIR=${SRC_DIR}"

  if [[ ! -d "${SRC_DIR}/.git" ]]; then
    git clone "${REPO_URL}" "${SRC_DIR}"
  fi

  git -C "${SRC_DIR}" config http.version HTTP/1.1
  if ! git -C "${SRC_DIR}" fetch --tags origin; then
    if git -C "${SRC_DIR}" rev-parse --verify -q "${REF}^{commit}" >/dev/null; then
      echo "WARN: fetch failed; using existing local ref ${REF}"
    else
      echo "ERROR: fetch failed and local ref ${REF} is unavailable" >&2
      exit 1
    fi
  fi
  git -C "${SRC_DIR}" checkout "${REF}"
  git -c http.version=HTTP/1.1 -C "${SRC_DIR}" submodule update --init --recursive

  cmake -S "${SRC_DIR}" -B "${SRC_DIR}/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DUAGENT_BUILD_EXAMPLES=OFF \
    -DUAGENT_BUILD_TESTS=OFF
  cmake --build "${SRC_DIR}/build" --parallel "$(nproc)"
  sudo cmake --install "${SRC_DIR}/build"
  sudo ldconfig

  echo "MicroXRCEAgent help:"
  MicroXRCEAgent -h | sed -n '1,20p' || true
  git -C "${SRC_DIR}" rev-parse HEAD | tee "${LOG_DIR}/microxrce_agent_commit.txt"
} | tee "${LOG_DIR}/microxrce_agent_build.log"
