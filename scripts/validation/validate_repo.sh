#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

cleanup_validation_caches() {
  find scripts tests -type d -name '__pycache__' -prune -exec rm -rf {} +
  rm -rf .pytest_cache
}
trap cleanup_validation_caches EXIT

echo "[1/15] Dependency lock and floating-ref validation"
python3 scripts/setup/verify_dependency_lock.py

echo "[2/15] Python compilation"
python3 -m compileall -q scripts tests

echo "[3/15] Shell syntax"
while IFS= read -r -d '' script; do
  bash -n "${script}"
done < <(find scripts docker -type f -name '*.sh' -print0)

echo "[4/15] JSON parsing"
git ls-files '*.json' -z | xargs -0 -r -n100 jq empty

echo "[5/15] YAML parsing"
python3 - <<'PY'
from pathlib import Path
import subprocess
import yaml

repo = Path.cwd()
raw = subprocess.run(
    ["git", "ls-files", "-z", "*.yaml", "*.yml"],
    check=True,
    capture_output=True,
).stdout
for item in raw.split(b"\0"):
    if not item:
        continue
    path = repo / item.decode("utf-8", errors="surrogateescape")
    with path.open("r", encoding="utf-8") as handle:
        yaml.safe_load(handle)
PY

echo "[6/15] Narrative uniqueness and legacy-headline scan"
mapfile -t narrative_files < <(git ls-files docs/narrative)
expected_narratives=(
  docs/narrative/CURRENT_NARRATIVE.md
  docs/narrative/NEW_NARRATIVE_v7.md
  docs/narrative/SCOPE.md
)
if [[ "${narrative_files[*]}" != "${expected_narratives[*]}" ]]; then
  printf 'unexpected narrative files: %s\n' "${narrative_files[*]}" >&2
  exit 1
fi
if [[ -n "$(git ls-files archive/pre_v4_baton)" ]]; then
  echo "archive/pre_v4_baton must not be tracked" >&2
  exit 1
fi
legacy_pattern='BATON current narrative|F1/F2/F2a current priority|old S1.?S4 current plan|mc_nn catastrophic differential as current headline|RAPTOR campaign as current headline|legacy multi-oracle paper plan'
if git grep -n -I -i -E "${legacy_pattern}" -- README.md AGENT.md docs scripts \
  ':(exclude)scripts/validation/validate_repo.sh'; then
  echo "legacy current-work headline found" >&2
  exit 1
fi

echo "[7/15] Family A import boundary"
family_a_files="$(git ls-files scripts/behavior scripts/adapters scripts/probes scripts/tracing)"
if [[ -n "${family_a_files}" ]] && printf '%s\n' "${family_a_files}" | xargs -r grep -nEi 'RaptorStatus|mc_nn|theta_genome|property[ _-]*P[1-7]' ; then
  echo "Family A code imports or embeds a Family B/legacy contract" >&2
  exit 1
fi

echo "[8/15] Active Markdown links"
python3 scripts/validation/check_markdown_links.py

echo "[9/15] TSV, JSON-schema, behavior, adapter, patch, and repository tests"
python3 scripts/validation/check_family_a_fuzzer_v0_preregistration.py
python3 scripts/validation/check_family_a_fuzzer_v0_activation_review.py
python3 scripts/validation/check_family_a_fuzzer_v0_readiness_amendment.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="${REPO_ROOT}" python3 -m pytest -q -p no:cacheprovider tests

echo "[10/15] Whitespace errors"
git diff --check
git diff --cached --check

echo "[11/15] Tracked ignored-file audit"
tracked_ignored="$(git ls-files -ci --exclude-standard)"
if [[ -n "${tracked_ignored}" ]]; then
  printf '%s\n' "${tracked_ignored}" >&2
  echo "tracked ignored files are forbidden" >&2
  exit 1
fi

echo "[12/15] Unexpected untracked-file audit"
untracked="$(git ls-files --others --exclude-standard)"
if [[ -n "${untracked}" ]]; then
  printf '%s\n' "${untracked}" >&2
  echo "unexpected untracked files are forbidden" >&2
  exit 1
fi

echo "[13/15] Tracked raw-run audit"
tracked_runs="$(git ls-files runs)"
if [[ -n "${tracked_runs}" ]]; then
  printf '%s\n' "${tracked_runs}" >&2
  echo "raw runs must not be tracked" >&2
  exit 1
fi

echo "[14/15] Tracked large-file audit"
large=0
while IFS= read -r -d '' path; do
  size="$(stat -c %s -- "${path}")"
  if (( size > 10485760 )); then
    printf '%s\t%s\n' "${size}" "${path}" >&2
    large=1
  fi
done < <(git ls-files -z)
if (( large != 0 )); then
  echo "tracked files over 10 MiB are forbidden" >&2
  exit 1
fi

echo "[15/15] Repository boundary summary"
printf 'narratives=%s archive_files=0 tracked_runs=0\n' "${#narrative_files[@]}"

echo "repository validation passed"
