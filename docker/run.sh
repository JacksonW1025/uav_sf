#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-uav_sf:family-a}"
CONTAINER_NAME="${CONTAINER_NAME:-uav_sf_family_a}"

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    docker_cmd=(sudo docker)
  else
    echo "docker is not usable by this user and sudo is unavailable" >&2
    exit 1
  fi
fi

env_args=(
  -e "PX4_DIR=/workspace/external/PX4-Autopilot"
  -e "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
)

for name in HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy; do
  value="${!name:-}"
  if [[ -n "${value}" ]]; then
    env_args+=(-e "${name}=${value}")
  fi
done

if [[ -n "${DISPLAY:-}" ]]; then
  env_args+=(-e "DISPLAY=${DISPLAY}" -v "/tmp/.X11-unix:/tmp/.X11-unix:rw")
fi

tty_args=()
if [[ -t 0 && -t 1 ]]; then
  tty_args=(-it)
fi

cpu_args=()
if [[ -n "${DOCKER_CPUSET_CPUS:-}" ]]; then
  cpu_args=(--cpuset-cpus "${DOCKER_CPUSET_CPUS}")
fi

"${docker_cmd[@]}" run --rm "${tty_args[@]}" \
  --name "${CONTAINER_NAME}" \
  --network host \
  --ipc host \
  "${cpu_args[@]}" \
  "${env_args[@]}" \
  -v "${REPO_ROOT}:/workspace" \
  -w /workspace \
  "${IMAGE_NAME}" \
  "$@"
