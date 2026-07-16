#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-uav_sf:family-a}"
LOCK_HELPER="${REPO_ROOT}/scripts/setup/verify_dependency_lock.py"
LOCK_FILE="${DEPENDENCY_LOCK_FILE:-${REPO_ROOT}/config/dependencies.lock.yaml}"
locked_image="$(python3 "${LOCK_HELPER}" --lock "${LOCK_FILE}" --get container.base_image)"
locked_digest="$(python3 "${LOCK_HELPER}" --lock "${LOCK_FILE}" --get container.base_image_digest)"
BASE_IMAGE="${BASE_IMAGE:-${locked_image}@${locked_digest}}"
HOST_USER="${HOST_USER:-${SUDO_USER:-${USER:-}}}"
if [[ -n "${HOST_USER}" ]] && id "${HOST_USER}" >/dev/null 2>&1; then
  default_uid="$(id -u "${HOST_USER}")"
  default_gid="$(id -g "${HOST_USER}")"
else
  default_uid="$(id -u)"
  default_gid="$(id -g)"
fi
USER_UID="${USER_UID:-${default_uid}}"
USER_GID="${USER_GID:-${default_gid}}"
CONTAINER_USER="${CONTAINER_USER:-px4}"

docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    docker_cmd=(sudo docker)
  else
    echo "docker is not usable by this user and sudo is unavailable" >&2
    exit 1
  fi
fi

proxy_args=()
for name in HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy; do
  value="${!name:-}"
  if [[ -n "${value}" ]]; then
    proxy_args+=(--build-arg "${name}=${value}")
  fi
done

"${docker_cmd[@]}" build \
  --network host \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  --build-arg "USERNAME=${CONTAINER_USER}" \
  --build-arg "USER_UID=${USER_UID}" \
  --build-arg "USER_GID=${USER_GID}" \
  "${proxy_args[@]}" \
  -t "${IMAGE_NAME}" \
  -f "${REPO_ROOT}/docker/Dockerfile" \
  "${REPO_ROOT}"

echo "Built ${IMAGE_NAME}"
