#!/usr/bin/env python3
"""Machine-verifiable contract for the sole Family A Jazzy environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
CONTAINER_DIR = ROOT / "containers/family_a_fuzzer_v0"
READINESS_DIR = ROOT / "experiments/fuzzer_v0/family_a/full_readiness"
EXPECTED_INDEX = "sha256:31daab66eef9139933379fb67159449944f4e2dcf2e22c2d12cc715f29873e0f"
EXPECTED_PLATFORM = "sha256:b82a5ba3869a81196414cf34e4fc25c7935aab78b1f5187570ca9362c478cdbd"
EXPECTED_MACHINE = "aarch64"
WORKSPACE = Path("/opt/family_a/workspace")


class EnvironmentContractError(RuntimeError):
    """The selected process is not the locked formal environment."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def _command_check(
    checks: list[dict[str, Any]],
    check_id: str,
    command: list[str],
    *,
    expected: str,
    contains: str | None = None,
) -> None:
    process = _run(*command)
    observed = (process.stdout + process.stderr).strip()
    passed = process.returncode == 0 and (contains is None or contains in observed)
    checks.append(
        {
            "check_id": check_id,
            "command": command,
            "expected": expected,
            "observed": observed[-4000:],
            "exit_code": process.returncode,
            "status": "PASS" if passed else "FAIL",
            "runtime_started": False,
        }
    )


def _value_check(
    checks: list[dict[str, Any]],
    check_id: str,
    observed: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "command": ["internal-value-check"],
            "expected": expected,
            "observed": observed,
            "exit_code": 0 if observed == expected else 1,
            "status": "PASS" if observed == expected else "FAIL",
            "runtime_started": False,
        }
    )


def _parse_lock(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _verify_package_locks(checks: list[dict[str, Any]]) -> None:
    expected = _parse_lock(CONTAINER_DIR / "apt-packages.lock") + _parse_lock(
        CONTAINER_DIR / "ros-packages.lock"
    )
    mismatches: list[str] = []
    for specification in expected:
        package, version = specification.split("=", 1)
        process = _run("dpkg-query", "-W", "-f=${Version}", package)
        if process.returncode or process.stdout != version:
            mismatches.append(
                f"{package}: expected={version} observed={process.stdout.strip() or 'MISSING'}"
            )
    checks.append(
        {
            "check_id": "exact_debian_and_ros_packages",
            "command": ["dpkg-query", "--locked-package-set"],
            "expected": f"{len(expected)} exact package versions",
            "observed": mismatches or f"{len(expected)} exact package versions",
            "exit_code": 0 if not mismatches else 1,
            "status": "PASS" if not mismatches else "FAIL",
            "runtime_started": False,
        }
    )


def _verify_sources(checks: list[dict[str, Any]]) -> None:
    lock = yaml.safe_load(
        (CONTAINER_DIR / "source-commits.lock.yaml").read_text(encoding="utf-8")
    )
    locations = {
        "PX4": WORKSPACE / "src/PX4-Autopilot",
        "px4_msgs": WORKSPACE / "ros/src/px4_msgs",
        "px4_ros2_interface_lib": WORKSPACE / "ros/src/px4_ros2_interface_lib",
        "Micro_XRCE_DDS_Agent": WORKSPACE / "src/Micro-XRCE-DDS-Agent",
    }
    for name, location in locations.items():
        process = _run("git", "-C", str(location), "rev-parse", "HEAD")
        _value_check(
            checks,
            f"source_commit_{name}",
            process.stdout.strip() if process.returncode == 0 else "MISSING",
            lock["sources"][name]["commit"],
        )


def _binary_manifest_root(repository: Path) -> Path | None:
    candidates = [
        Path(os.environ.get("FAMILY_A_AUTHORIZATION_REPO", ""))
        / "experiments/fuzzer_v0/family_a/full_readiness",
        repository / "experiments/fuzzer_v0/family_a/full_readiness",
    ]
    for candidate in candidates:
        if (candidate / "binary_manifest.json").is_file():
            return candidate
    return None


def _verify_binary_manifest(
    checks: list[dict[str, Any]], repository: Path, build_time: bool
) -> None:
    manifest_root = _binary_manifest_root(repository)
    if manifest_root is None:
        _value_check(
            checks,
            "binary_manifest",
            "NOT_GENERATED_DURING_IMAGE_BUILD" if build_time else "MISSING",
            "NOT_GENERATED_DURING_IMAGE_BUILD" if build_time else "MATCH",
        )
        return
    manifest = json.loads(
        (manifest_root / "binary_manifest.json").read_text(encoding="utf-8")
    )
    mismatches: list[str] = []
    for record in manifest.get("binaries", []):
        path = Path(record["output_path"])
        if not path.is_file():
            mismatches.append(f"missing:{path}")
        elif sha256(path) != record["sha256"]:
            mismatches.append(f"hash:{path}")
        if record.get("architecture") != "aarch64":
            mismatches.append(f"architecture:{path}")
        if record.get("ros_distro") != "jazzy":
            mismatches.append(f"ros_distro:{path}")
    checks.append(
        {
            "check_id": "binary_manifest",
            "command": ["sha256", "all-formal-binaries"],
            "expected": "MATCH",
            "observed": mismatches or "MATCH",
            "exit_code": 0 if not mismatches else 1,
            "status": "PASS" if not mismatches else "FAIL",
            "runtime_started": False,
        }
    )


def verify(repository: Path = ROOT, *, build_time: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    _value_check(checks, "formal_container_marker", os.getenv("FAMILY_A_FORMAL_CONTAINER"), "1")
    _value_check(checks, "ros_distribution", os.getenv("ROS_DISTRO"), "jazzy")
    _value_check(
        checks, "rmw_implementation", os.getenv("RMW_IMPLEMENTATION"), "rmw_fastrtps_cpp"
    )
    _value_check(checks, "architecture", platform.machine(), EXPECTED_MACHINE)

    dockerfile = (CONTAINER_DIR / "Dockerfile").read_text(encoding="utf-8")
    source_lock = (CONTAINER_DIR / "source-commits.lock.yaml").read_text(
        encoding="utf-8"
    )
    _value_check(
        checks,
        "base_index_digest",
        EXPECTED_INDEX in dockerfile and EXPECTED_INDEX in source_lock,
        True,
    )
    _value_check(
        checks,
        "base_platform_digest",
        EXPECTED_PLATFORM in dockerfile and EXPECTED_PLATFORM in source_lock,
        True,
    )
    floating_from = any(
        re.match(r"^\s*FROM\s+\S+:[^@\s]+\s*$", line)
        for line in dockerfile.splitlines()
    )
    _value_check(checks, "no_floating_final_base", floating_from, False)

    prefixes = {
        name: os.getenv(name, "")
        for name in (
            "AMENT_PREFIX_PATH",
            "CMAKE_PREFIX_PATH",
            "COLCON_PREFIX_PATH",
            "PYTHONPATH",
            "ROS_PACKAGE_PATH",
        )
    }
    leakage = [
        f"{name}={value}"
        for name, value in prefixes.items()
        if "humble" in value.lower() or "/home/" in value or "/mnt/" in value
    ]
    _value_check(checks, "no_host_ros_leakage", leakage, [])

    _command_check(checks, "ros2_help", ["ros2", "--help"], expected="exit 0")
    _command_check(checks, "gazebo_identity", ["gz", "--versions"], expected="exit 0")
    _command_check(checks, "python_identity", ["python3", "--version"], expected="exit 0")
    _command_check(checks, "compiler_identity", ["gcc", "--version"], expected="exit 0")
    _command_check(checks, "cmake_identity", ["cmake", "--version"], expected="exit 0")
    _command_check(checks, "colcon_identity", ["colcon", "list", "--help"], expected="exit 0")
    _command_check(checks, "vcstool_identity", ["vcs", "--help"], expected="exit 0")
    _command_check(checks, "rosdep_identity", ["rosdep", "--version"], expected="exit 0")

    for package in (
        "rclcpp",
        "rclpy",
        "rmw_fastrtps_cpp",
        "ros_gz_sim",
        "px4_msgs",
        "px4_ros2_cpp",
        "px4_ros2_py",
        "route_transition_external_mode",
    ):
        _command_check(
            checks,
            f"ros_package_{package}",
            ["ros2", "pkg", "prefix", package],
            expected="package prefix exists",
        )
    for module in (
        "rclpy",
        "px4_msgs.msg",
        "px4_ros2",
        "jsonschema",
        "yaml",
        "scripts.fuzzer_v0.family_a.state_space_evaluator",
        "scripts.tracing.route_trace_collector",
        "scripts.tracing.clock_bridge_collector",
        "scripts.oracles.route_oracle_v0",
        "scripts.oracles.pre_revocation_freshness_oracle",
        "scripts.oracles.successor_progression_oracle",
        "scripts.oracles.authority_event_linearization_oracle",
    ):
        _command_check(
            checks,
            f"python_import_{module}",
            ["python3", "-c", f"import {module}"],
            expected="import succeeds",
        )

    required_paths = (
        WORKSPACE / "src/PX4-Autopilot/build/px4_sitl_default/bin/px4",
        WORKSPACE
        / "ros/install/lib/route_transition_external_mode/c1_concurrency_probe",
        WORKSPACE / "ros/install/lib/route_transition_external_mode/route_transition_external_mode",
        WORKSPACE / "ros/install/lib/route_transition_external_mode/p0_external_mode_executor",
        WORKSPACE / "dds/MicroXRCEAgent",
    )
    for path in required_paths:
        _value_check(checks, f"binary_exists_{path.name}", path.is_file(), True)
        if path.is_file():
            process = _run("ldd", str(path))
            linked = process.stdout + process.stderr
            host_link = "/home/" in linked or "/mnt/" in linked or "humble" in linked.lower()
            _value_check(checks, f"linked_libraries_container_{path.name}", host_link, False)

    _verify_package_locks(checks)
    _verify_sources(checks)
    _verify_binary_manifest(checks, repository, build_time)

    failed = [item["check_id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "1.0",
        "environment_id": "FAMILY_A_FUZZER_V0_JAZZY_ARM64",
        "status": "PASS" if not failed else "FAIL",
        "container_base_index_digest": EXPECTED_INDEX,
        "container_base_platform_digest": EXPECTED_PLATFORM,
        "runtime_started": False,
        "formal_flight_communication_started": False,
        "failed_checks": failed,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--repository", type=Path, default=ROOT)
    verify_parser.add_argument("--build-time", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    result = verify(args.repository, build_time=bool(args.build_time))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
