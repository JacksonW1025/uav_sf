#!/usr/bin/env python3
"""Prepare detached, commit-pinned source trees and apply verified patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
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


def _run_network(*args: str, cwd: Path | None = None) -> None:
    last_error: subprocess.SubprocessError | None = None
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_HTTP_LOW_SPEED_LIMIT": "1024",
            "GIT_HTTP_LOW_SPEED_TIME": "30",
        }
    )
    timeout_s = 900 if "submodule" in args else 120
    for attempt in range(1, 4):
        try:
            subprocess.run(
                list(args),
                cwd=cwd or ROOT,
                check=True,
                text=True,
                env=environment,
                timeout=timeout_s,
            )
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt)
    assert last_error is not None
    raise last_error


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
    created = not target.exists()
    if created:
        target.mkdir(parents=True)
        _run("git", "init", "--quiet", cwd=target)
        _run("git", "remote", "add", "origin", repository, cwd=target)
    current = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=target,
        text=True,
        capture_output=True,
    )
    if current.returncode != 0:
        _run_network("git", "fetch", "--depth", "1", "origin", commit, cwd=target)
        _run("git", "checkout", "--detach", "--quiet", "FETCH_HEAD", cwd=target)
    if _run("git", "rev-parse", "HEAD", cwd=target, capture=True) != commit:
        raise SourceError(f"{name}: checkout is not at its locked commit")
    if _run("git", "remote", "get-url", "origin", cwd=target, capture=True) != repository:
        raise SourceError(f"{name}: origin differs from the lock")
    return target


def _patch_paths(path: Path) -> set[str]:
    expression = re.compile(r"^diff --git a/(.+) b/(.+)$")
    paths: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = expression.match(line)
        if match is not None:
            paths.add(match.group(2))
    if not paths:
        raise SourceError(f"patch has no file entries: {path.relative_to(ROOT)}")
    return paths


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


def _verify_patched_tree(source: Path, allowed_paths: set[str], name: str) -> None:
    _run("git", "diff", "--check", cwd=source)
    # Do not route porcelain output through `_run(..., capture=True)`: that
    # helper strips leading whitespace, while the first porcelain status
    # column is itself significant (for example `` M path``).  Losing that
    # byte silently removes the first character of the first path.
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    observed = {
        line[3:].split(" -> ", 1)[-1]
        for line in status.splitlines()
        if len(line) > 3
    }
    if observed != allowed_paths:
        unexpected = sorted(observed - allowed_paths)
        missing = sorted(allowed_paths - observed)
        raise SourceError(
            f"{name}: patched worktree differs; unexpected={unexpected}, missing={missing}"
        )


def _prepare_px4_submodules(source: Path) -> int:
    _run("git", "submodule", "sync", "--recursive", cwd=source)
    # The superproject fixes every submodule SHA.  A depth-one checkout of
    # those exact objects is sufficient for SITL and avoids importing years
    # of unrelated NuttX, simulator, and board history into the image.
    _run_network(
        "git",
        "submodule",
        "update",
        "--init",
        "--recursive",
        "--depth",
        "1",
        "--jobs",
        "8",
        cwd=source,
    )
    status = _run("git", "submodule", "status", "--recursive", cwd=source, capture=True)
    lines = [line for line in status.splitlines() if line.strip()]
    invalid = [line for line in lines if line[0] in {"-", "+", "U"}]
    if invalid:
        raise SourceError("PX4 submodule identity is incomplete or differs from the lock")
    return len(lines)


def prepare(output_root: Path, *, with_px4_submodules: bool = False) -> dict[str, Any]:
    locks = _load(SOURCE_LOCK)
    patch_lock = _load(PATCH_LOCK)
    output_root.mkdir(parents=True, exist_ok=True)
    trees = {
        name: prepare_source(name, record, output_root)
        for name, record in locks["sources"].items()
    }
    allowed_by_source: dict[str, set[str]] = {name: set() for name in trees}
    for record in patch_lock["patches"]:
        patch_path = ROOT / record["path"]
        apply_patch(
            trees[record["source"]],
            patch_path,
            record["sha256"],
        )
        allowed_by_source[record["source"]].update(_patch_paths(patch_path))
    for name, source in trees.items():
        _verify_patched_tree(source, allowed_by_source[name], name)
    submodule_count = 0
    if with_px4_submodules:
        submodule_count = _prepare_px4_submodules(trees["PX4-Autopilot"])
    return {
        "sources": {name: str(path) for name, path in trees.items()},
        "px4_submodules_initialized": with_px4_submodules,
        "px4_submodule_count": submodule_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "external")
    parser.add_argument("--with-px4-submodules", action="store_true")
    args = parser.parse_args()
    try:
        result = prepare(
            args.output_root.resolve(),
            with_px4_submodules=args.with_px4_submodules,
        )
    except (OSError, KeyError, ValueError, SourceError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
