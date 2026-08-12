#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repository_root"

python3 -m scripts.validation.validate_repo
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v

while IFS= read -r -d '' shell_file; do
  bash -n "$shell_file"
done < <(find scripts -type f -name '*.sh' -print0)

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
  git diff --cached --check
fi

echo "REPOSITORY VALIDATION PASS"
