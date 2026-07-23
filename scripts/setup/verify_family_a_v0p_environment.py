#!/usr/bin/env python3
"""Statically verify the reproducible ROS Jazzy V0-P environment contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = (
    ROOT / "experiments/fuzzer_v0/family_a/readiness_amendment/environment_lock.yaml"
)
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return value


def validate(path: Path = LOCK_PATH) -> dict[str, Any]:
    errors: list[str] = []
    lock = _yaml(path)
    dependency = _yaml(ROOT / "config/dependencies.lock.yaml")
    if lock.get("schema_version") != "1.0":
        errors.append("environment schema_version must be 1.0")
    if lock.get("environment_kind") != "LOCKED_REPRODUCIBLE_CONTAINER":
        errors.append("environment_kind is not the locked container contract")
    if lock.get("ros_distribution") != "jazzy":
        errors.append("ROS distribution is not jazzy")
    if lock.get("gazebo_distribution") != "harmonic":
        errors.append("Gazebo distribution is not harmonic")
    if lock.get("architecture") != dependency["experiment_environment"]["architecture"]:
        errors.append("architecture differs from the dependency lock")
    if lock.get("python_identity") != dependency["experiment_environment"]["python"]:
        errors.append("Python identity differs from the dependency lock")
    if lock.get("base_image") != dependency["container"]["base_image"]:
        errors.append("base image name differs from the dependency lock")
    if lock.get("base_image_digest") != dependency["container"]["base_image_digest"]:
        errors.append("base image digest differs from the dependency lock")
    if not DIGEST.fullmatch(str(lock.get("base_image_digest", ""))):
        errors.append("base image digest is not exact")

    for field, dependency_name in (
        ("PX4", "px4_autopilot"),
        ("px4_msgs", "px4_msgs"),
        ("px4_ros2_interface_lib", "px4_ros2_interface_lib"),
        ("Micro_XRCE_DDS_Agent", "micro_xrce_dds_agent"),
    ):
        observed = lock.get("workspace_identity", {}).get(field)
        expected = dependency[dependency_name]["commit"]
        if observed != expected or not COMMIT.fullmatch(str(observed or "")):
            errors.append(f"{field} identity differs from the dependency lock")

    identities = lock.get("file_identities")
    if not isinstance(identities, list) or not identities:
        errors.append("environment file identities are missing")
    else:
        for item in identities:
            candidate = ROOT / str(item.get("path", ""))
            if not candidate.is_file():
                errors.append(f"missing environment file: {item.get('path')}")
            elif sha256(candidate) != item.get("sha256"):
                errors.append(f"environment file hash mismatch: {item.get('path')}")

    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    required_docker_tokens = (
        "ROS_DISTRO=jazzy",
        "ros-jazzy-ros-base",
        "gz-harmonic",
        "source /opt/ros/jazzy/setup.bash",
    )
    for token in required_docker_tokens:
        if token not in dockerfile:
            errors.append(f"Dockerfile is missing: {token}")
    setup_path = ROOT / str(lock.get("setup_script_path", ""))
    if not setup_path.is_file():
        errors.append("setup script is missing")
    else:
        process = subprocess.run(
            ["bash", "-n", str(setup_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if process.returncode:
            errors.append("setup script syntax check failed")
    dependency_check = subprocess.run(
        [sys.executable, "scripts/setup/verify_dependency_lock.py", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if dependency_check.returncode:
        errors.append("dependency lock validation failed")

    status = (
        "STATICALLY_AVAILABLE"
        if not errors and lock.get("status") == "STATICALLY_AVAILABLE"
        else "BLOCKED"
    )
    return {
        "schema_version": "1.0",
        "status": status,
        "errors": errors,
        "environment_kind": lock.get("environment_kind"),
        "ros_distribution": lock.get("ros_distribution"),
        "base_image_digest": lock.get("base_image_digest"),
        "host_observation": {
            "architecture": platform.machine(),
            "qualification_environment_selected": False,
        },
        "runtime_started": False,
        "flight_communication_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(args.lock)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Family A V0-P ROS Jazzy environment: {result['status']}")
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["status"] == "STATICALLY_AVAILABLE" else 1


if __name__ == "__main__":
    sys.exit(main())
