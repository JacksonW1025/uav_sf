#!/usr/bin/env python3
"""Validate, query, or explicitly update the dependency lock."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = REPO_ROOT / "config" / "dependencies.lock.yaml"
DEPENDENCIES = (
    "px4_autopilot",
    "px4_msgs",
    "px4_ros2_interface_lib",
    "micro_xrce_dds_agent",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
FLOATING_REFS = {"head", "main", "master", "latest", "stable", "develop", "development"}


def load_lock(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError("lock root must be a mapping")
    return value


def valid_repository_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc == "github.com" and parsed.path.endswith(".git")


def validate(lock: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if lock.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")

    for name in DEPENDENCIES:
        entry = lock.get(name)
        if not isinstance(entry, dict):
            errors.append(f"missing dependency mapping: {name}")
            continue
        if not valid_repository_url(entry.get("repository")):
            errors.append(f"{name}.repository must be an HTTPS GitHub .git URL")
        commit = entry.get("commit")
        if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
            errors.append(f"{name}.commit must be a lowercase 40-character SHA")
        elif commit.lower() in FLOATING_REFS:
            errors.append(f"{name}.commit is floating")
        for field in ("source", "selection_reason"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{name}.{field} is required")

    container = lock.get("container")
    if not isinstance(container, dict):
        errors.append("missing container mapping")
    else:
        image = container.get("base_image")
        if not isinstance(image, str) or image.endswith(":latest"):
            errors.append("container.base_image must be named and must not use latest")
        for field in ("base_image_digest", "platform_digest"):
            if not isinstance(container.get(field), str) or not DIGEST_RE.fullmatch(container[field]):
                errors.append(f"container.{field} must be a sha256 digest")
        if container.get("ros_distro") != "jazzy":
            errors.append("container.ros_distro must be jazzy")
        if container.get("gazebo_distribution") != "harmonic":
            errors.append("container.gazebo_distribution must be harmonic")

    environment = lock.get("experiment_environment")
    if not isinstance(environment, dict):
        errors.append("missing experiment_environment mapping")
    else:
        for field in ("architecture", "compiler", "cmake", "python"):
            if not isinstance(environment.get(field), str) or not environment[field].strip():
                errors.append(f"experiment_environment.{field} is required")
    return errors


def dotted_get(lock: dict[str, Any], key: str) -> Any:
    value: Any = lock
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(key)
        value = value[part]
    return value


def remote_head(repository: str) -> str:
    process = subprocess.run(
        ["git", "ls-remote", repository, "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    )
    sha = process.stdout.split()[0]
    if not SHA_RE.fullmatch(sha):
        raise RuntimeError(f"remote HEAD did not resolve to a full SHA: {repository}")
    return sha


def update_dependencies(path: Path, lock: dict[str, Any], names: list[str]) -> None:
    unknown = sorted(set(names) - set(DEPENDENCIES))
    if unknown:
        raise ValueError("unknown dependencies: " + ", ".join(unknown))
    for name in names:
        entry = lock[name]
        entry["commit"] = remote_head(entry["repository"])
        entry["source"] = "origin HEAD resolved by explicit --update-lock"
        entry["selection_reason"] = "Explicit lock refresh requested by the operator; revalidation is required."
        if "describe" in entry:
            entry["describe"] = entry["commit"][:12]
    lock["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(lock, handle, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--get", metavar="DOTTED_KEY")
    parser.add_argument("--json", action="store_true", help="print a machine-readable validation result")
    parser.add_argument(
        "--update-lock",
        action="append",
        default=[],
        metavar="DEPENDENCY",
        help="explicitly replace one dependency commit with its remote HEAD",
    )
    args = parser.parse_args()

    lock = load_lock(args.lock)
    if args.update_lock:
        update_dependencies(args.lock, lock, args.update_lock)
        lock = load_lock(args.lock)

    errors = validate(lock)
    if args.get:
        if errors:
            raise SystemExit("invalid dependency lock: " + "; ".join(errors))
        value = dotted_get(lock, args.get)
        print(json.dumps(value) if isinstance(value, (dict, list)) else value)
        return 0

    result = {"status": "PASS" if not errors else "FAIL", "errors": errors, "lock": str(args.lock)}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        print("dependency lock validation failed:")
        for error in errors:
            print(f"- {error}")
    else:
        print("dependency lock validation passed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
