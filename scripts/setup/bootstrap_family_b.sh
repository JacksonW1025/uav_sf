#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_LOCK=0
VALIDATE_ONLY=0
while (($#)); do
  case "$1" in
    --update-lock) UPDATE_LOCK=1; shift ;;
    --validate-only) VALIDATE_ONLY=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

args=()
if ((UPDATE_LOCK)); then args+=(--update-lock); fi
if ((VALIDATE_ONLY)); then args+=(--validate-only); fi
"${REPO_ROOT}/scripts/setup/bootstrap_family_a.sh" "${args[@]}"
if ((VALIDATE_ONLY)); then
  test -f "${REPO_ROOT}/family_b/README.md"
  test -f "${REPO_ROOT}/family_b/boards/mcnn_sih.px4board"
  test -f "${REPO_ROOT}/family_b/boards/raptor_sih.px4board"
  echo "Family B optional asset contract validated"
  exit 0
fi

# The profile fetches optional upstream submodules but deliberately does not
# apply the retained, not-yet-revalidated overlays or state shim.
"${REPO_ROOT}/scripts/setup/clone_px4.sh" --profile family_b
echo "Family B dependency layer prepared; revalidate family_b assets before use"
