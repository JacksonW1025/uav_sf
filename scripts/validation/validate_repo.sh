#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

cleanup_validation_caches() {
  find scripts tests -type d -name '__pycache__' -prune -exec rm -rf {} +
  rm -rf .pytest_cache
}
trap cleanup_validation_caches EXIT

echo "[1/10] Python compilation"
python3 -m compileall -q scripts tests

echo "[2/10] Shell syntax"
while IFS= read -r -d '' script; do
  bash -n "${script}"
done < <(find scripts docker -type f -name '*.sh' -print0)

echo "[3/10] JSON parsing"
git ls-files '*.json' -z | xargs -0 -r -n100 jq empty

echo "[4/10] YAML parsing"
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

echo "[5/10] Active Markdown links"
python3 scripts/validation/check_markdown_links.py

echo "[6/10] Unit tests"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="${REPO_ROOT}" python3 -m pytest -q -p no:cacheprovider tests

echo "[7/10] Whitespace errors"
git diff --check
git diff --cached --check

echo "[8/10] Tracked ignored-file audit"
tracked_ignored="$(git ls-files -ci --exclude-standard)"
if [[ -n "${tracked_ignored}" ]]; then
  printf '%s\n' "${tracked_ignored}" >&2
  echo "tracked ignored files are forbidden" >&2
  exit 1
fi

echo "[9/10] Unexpected untracked-file audit"
untracked="$(git ls-files --others --exclude-standard)"
if [[ -n "${untracked}" ]]; then
  printf '%s\n' "${untracked}" >&2
  echo "unexpected untracked files are forbidden" >&2
  exit 1
fi

echo "[10/10] Tracked large-file audit"
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

echo "repository validation passed"
