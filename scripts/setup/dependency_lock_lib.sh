#!/usr/bin/env bash

if [[ -z "${REPO_ROOT:-}" ]]; then
  echo "REPO_ROOT must be set before sourcing dependency_lock_lib.sh" >&2
  exit 2
fi

DEPENDENCY_LOCK_FILE="${DEPENDENCY_LOCK_FILE:-${REPO_ROOT}/config/dependencies.lock.yaml}"
LOCK_HELPER="${REPO_ROOT}/scripts/setup/verify_dependency_lock.py"

lock_verify() {
  python3 "${LOCK_HELPER}" --lock "${DEPENDENCY_LOCK_FILE}"
}

lock_get() {
  python3 "${LOCK_HELPER}" --lock "${DEPENDENCY_LOCK_FILE}" --get "$1"
}

canonical_git_url() {
  local url="$1"
  url="${url%/}"
  url="${url%.git}"
  printf '%s\n' "${url,,}"
}

verify_remote_url() {
  local directory="$1"
  local expected="$2"
  local actual
  actual="$(git -C "${directory}" remote get-url origin)"
  if [[ "$(canonical_git_url "${actual}")" != "$(canonical_git_url "${expected}")" ]]; then
    echo "remote mismatch for ${directory}: expected ${expected}, got ${actual}" >&2
    exit 20
  fi
}

verify_clean_repository() {
  local directory="$1"
  local dirty
  dirty="$(git -C "${directory}" status --porcelain)"
  if [[ -n "${dirty}" ]]; then
    printf '%s\n' "${dirty}" >&2
    echo "dependency repository is dirty: ${directory}" >&2
    exit 21
  fi
}

checkout_locked_repository() {
  local name="$1"
  local directory="$2"
  local repository commit actual
  repository="$(lock_get "${name}.repository")"
  commit="$(lock_get "${name}.commit")"

  if [[ ! -d "${directory}/.git" ]]; then
    mkdir -p "$(dirname "${directory}")"
    git -c http.version=HTTP/1.1 clone --no-checkout "${repository}" "${directory}"
  fi
  verify_remote_url "${directory}" "${repository}"
  verify_clean_repository "${directory}"
  git -c http.version=HTTP/1.1 -C "${directory}" fetch origin "${commit}"
  git -C "${directory}" checkout --detach "${commit}"
  actual="$(git -C "${directory}" rev-parse HEAD)"
  if [[ "${actual}" != "${commit}" ]]; then
    echo "HEAD mismatch for ${name}: expected ${commit}, got ${actual}" >&2
    exit 22
  fi
  verify_clean_repository "${directory}"
}

log_repository_identity() {
  local name="$1"
  local directory="$2"
  local dirty="clean"
  if [[ -n "$(git -C "${directory}" status --porcelain)" ]]; then dirty="dirty"; fi
  printf '%s_COMMIT=%s\n' "${name}" "$(git -C "${directory}" rev-parse HEAD)"
  printf '%s_DIRTY=%s\n' "${name}" "${dirty}"
  printf '%s_REMOTE=%s\n' "${name}" "$(git -C "${directory}" remote get-url origin)"
}
