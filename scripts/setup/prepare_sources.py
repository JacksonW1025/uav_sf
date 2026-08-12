#!/usr/bin/env python3
"""Prepare detached, commit-pinned source trees and apply verified patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE_LOCK = ROOT / "config/dependencies.lock.json"
PATCH_LOCK = ROOT / "config/patches.lock.json"


class SourceError(RuntimeError):
    """A source tree or patch differs from its immutable identity."""


def _run(*args: str, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        list(args),
        cwd=cwd or ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SourceError(f"{path}: root must be an object")
    return value


def _tree_name(source_name: str) -> str:
    return source_name.lower().replace("-", "_")


def prepare_source(name: str, record: dict[str, str], root: Path) -> Path:
    target = root / _tree_name(name)
    commit = record["commit"]
    repository = record["repository"]
    if not target.exists():
        target.mkdir(parents=True)
        _run("git", "init", "--quiet", cwd=target)
        _run("git", "remote", "add", "origin", repository, cwd=target)
        _run("git", "fetch", "--depth", "1", "origin", commit, cwd=target)
        _run("git", "checkout", "--detach", "--quiet", "FETCH_HEAD", cwd=target)
    if _run("git", "rev-parse", "HEAD", cwd=target, capture=True) != commit:
        raise SourceError(f"{name}: checkout is not at its locked commit")
    if _run("git", "remote", "get-url", "origin", cwd=target, capture=True) != repository:
        raise SourceError(f"{name}: origin differs from the lock")
    return target


def apply_patch(source: Path, patch: Path, expected_hash: str) -> None:
    observed = hashlib.sha256(patch.read_bytes()).hexdigest()
    if observed != expected_hash:
        raise SourceError(f"patch hash mismatch: {patch.relative_to(ROOT)}")
    forward = subprocess.run(
        ["git", "apply", "--check", str(patch)], cwd=source, capture_output=True
    )
    if forward.returncode == 0:
        _run("git", "apply", str(patch), cwd=source)
        return
    reverse = subprocess.run(
        ["git", "apply", "--reverse", "--check", str(patch)],
        cwd=source,
        capture_output=True,
    )
    if reverse.returncode != 0:
        raise SourceError(f"patch cannot be applied cleanly: {patch.relative_to(ROOT)}")


def prepare(output_root: Path) -> dict[str, str]:
    locks = _load(SOURCE_LOCK)
    patch_lock = _load(PATCH_LOCK)
    output_root.mkdir(parents=True, exist_ok=True)
    trees = {
        name: prepare_source(name, record, output_root)
        for name, record in locks["sources"].items()
    }
    for record in patch_lock["patches"]:
        apply_patch(
            trees[record["source"]],
            ROOT / record["path"],
            record["sha256"],
        )
    return {name: str(path) for name, path in trees.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "external")
    args = parser.parse_args()
    try:
        result = prepare(args.output_root.resolve())
    except (OSError, KeyError, ValueError, SourceError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "sources": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
