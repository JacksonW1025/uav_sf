#!/usr/bin/env python3
"""Capture package and formal-binary identities from the locked container."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = Path("/opt/family_a/workspace")


class CaptureError(RuntimeError):
    """The running image is incomplete or not the formal Jazzy environment."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(*command: str, check: bool = True) -> str:
    process = subprocess.run(command, capture_output=True, text=True)
    if check and process.returncode:
        raise CaptureError(
            f"{' '.join(command)} failed: {(process.stdout + process.stderr).strip()}"
        )
    return (process.stdout + process.stderr).strip()


def _git_commit(path: Path) -> str:
    return _run("git", "-C", str(path), "rev-parse", "HEAD")


def _linked_libraries(path: Path) -> list[str]:
    process = subprocess.run(["ldd", str(path)], capture_output=True, text=True)
    if process.returncode:
        raise CaptureError(f"ldd failed for {path}: {process.stderr.strip()}")
    lines = [line.strip() for line in process.stdout.splitlines() if line.strip()]
    if any("not found" in line for line in lines):
        raise CaptureError(f"unresolved linked library for {path}")
    if any(
        token in line.lower()
        for line in lines
        for token in ("/home/", "/mnt/", "humble")
    ):
        raise CaptureError(f"host or Humble linkage detected for {path}")
    return lines


def _read_only_check(path: Path, binary_type: str) -> dict[str, Any]:
    command = ["test", "-r", str(path)]
    if binary_type in {"ELF_EXECUTABLE", "SHELL_ENTRY"}:
        command = ["test", "-x", str(path)]
    process = subprocess.run(command, capture_output=True, text=True)
    return {
        "command": " ".join(command),
        "exit_code": process.returncode,
        "status": "PASS" if process.returncode == 0 else "FAIL",
    }


def _binary(
    *,
    component_id: str,
    source_commit: str,
    source_path: str,
    build_target: str,
    build_command: str,
    build_flags: list[str],
    output_path: Path,
    binary_type: str,
) -> dict[str, Any]:
    if not output_path.is_file():
        raise CaptureError(f"formal output is missing: {output_path}")
    libraries = (
        _linked_libraries(output_path)
        if binary_type in {"ELF_EXECUTABLE", "ELF_SHARED_LIBRARY"}
        else []
    )
    read_only = _read_only_check(output_path, binary_type)
    if read_only["status"] != "PASS":
        raise CaptureError(f"read-only entry check failed: {output_path}")
    return {
        "component_id": component_id,
        "source_commit": source_commit,
        "source_path": source_path,
        "build_target": build_target,
        "build_command": build_command,
        "build_flags": build_flags,
        "output_path": str(output_path),
        "sha256": _sha256(output_path),
        "linked_libraries": libraries,
        "ros_distro": "jazzy",
        "rmw_implementation": "rmw_fastrtps_cpp",
        "architecture": "aarch64",
        "binary_type": binary_type,
        "read_only_entry_check": read_only,
    }


def _python_entry(
    component_id: str, source_path: str, implementation_commit: str
) -> dict[str, Any]:
    return _binary(
        component_id=component_id,
        source_commit=implementation_commit,
        source_path=source_path,
        build_target="python_compileall",
        build_command="python3 -m compileall -q scripts",
        build_flags=["PYTHONDONTWRITEBYTECODE=1"],
        output_path=ROOT / source_path,
        binary_type="PYTHON_ENTRY",
    )


def capture(image_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if os.getenv("FAMILY_A_FORMAL_CONTAINER") != "1":
        raise CaptureError("capture must run inside the formal container")
    if os.getenv("ROS_DISTRO") != "jazzy" or platform.machine() != "aarch64":
        raise CaptureError("capture environment is not Jazzy/aarch64")
    implementation = os.environ.get("FAMILY_A_IMPLEMENTATION_COMMIT", "")
    if len(implementation) != 40:
        raise CaptureError("image implementation commit is missing")
    px4_commit = _git_commit(WORKSPACE / "src/PX4-Autopilot")
    interface_commit = _git_commit(WORKSPACE / "ros/src/px4_ros2_interface_lib")
    agent_commit = _git_commit(WORKSPACE / "src/Micro-XRCE-DDS-Agent")
    ros_install = WORKSPACE / "ros/install"
    adapter_bin = ros_install / "lib/route_transition_external_mode"
    binaries = [
        _binary(
            component_id="px4_sitl",
            source_commit=px4_commit,
            source_path="PX4-Autopilot",
            build_target="px4_sitl_default",
            build_command="make -jN px4_sitl_default",
            build_flags=["default_PX4_RelWithDebInfo"],
            output_path=WORKSPACE
            / "src/PX4-Autopilot/build/px4_sitl_default/bin/px4",
            binary_type="ELF_EXECUTABLE",
        ),
        _binary(
            component_id="micro_xrce_dds_agent",
            source_commit=agent_commit,
            source_path="Micro-XRCE-DDS-Agent",
            build_target="MicroXRCEAgent",
            build_command="cmake --build /opt/family_a/workspace/dds --parallel N",
            build_flags=["UAGENT_SUPERBUILD=ON", "CMAKE_BUILD_TYPE=Release"],
            output_path=WORKSPACE / "dds/MicroXRCEAgent",
            binary_type="ELF_EXECUTABLE",
        ),
    ]
    for component_id, filename, source_path in (
        ("adapter_dynamic", "route_transition_external_mode", "src/external_mode.cpp"),
        ("adapter_executor", "p0_external_mode_executor", "src/p0_executor.cpp"),
        ("successor_executor", "successor_baseline_executor", "src/successor_baseline.cpp"),
        ("freshness_probe", "external_mode_freshness_probe", "src/freshness_probe.cpp"),
        ("adapter_c1", "c1_concurrency_probe", "src/c1_concurrency_probe.cpp"),
        ("issue162_replay", "issue162_replay", "src/issue162_replay.cpp"),
    ):
        binaries.append(
            _binary(
                component_id=component_id,
                source_commit=implementation,
                source_path=f"scripts/adapters/external_mode_adapter/{source_path}",
                build_target=filename,
                build_command="colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF",
                build_flags=["CMAKE_BUILD_TYPE=Release", "BUILD_TESTING=OFF"],
                output_path=adapter_bin / filename,
                binary_type="ELF_EXECUTABLE",
            )
        )
    binaries.append(
        _binary(
            component_id="px4_ros2_cpp",
            source_commit=interface_commit,
            source_path="px4_ros2_interface_lib",
            build_target="px4_ros2_cpp",
            build_command="colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF",
            build_flags=["CMAKE_BUILD_TYPE=Release", "BUILD_TESTING=OFF"],
            output_path=ros_install / "lib/libpx4_ros2_cpp.so",
            binary_type="ELF_SHARED_LIBRARY",
        )
    )
    for component_id, source_path in (
        ("evaluator_runner", "scripts/fuzzer_v0/family_a/state_space_evaluator.py"),
        ("formal_orchestrator", "scripts/fuzzer_v0/family_a/formal_orchestrator.py"),
        ("safety_supervisor", "scripts/fuzzer_v0/family_a/safety_supervisor.py"),
        ("live_telemetry", "scripts/fuzzer_v0/family_a/runtime_telemetry_collector.py"),
        ("freshness_collector", "scripts/fuzzer_v0/family_a/qualification_freshness_collector.py"),
        ("compact_evidence", "scripts/fuzzer_v0/family_a/compact_evidence.py"),
        ("evidence_gate", "scripts/fuzzer_v0/family_a/evidence_gate.py"),
        ("attempt_accounting", "scripts/fuzzer_v0/family_a/attempt_accounting.py"),
        ("comparison_strategies", "scripts/fuzzer_v0/family_a/strategies.py"),
        ("route_collector", "scripts/tracing/route_trace_collector.py"),
        ("writer_collector", "scripts/tracing/actuator_writer_collector.py"),
        ("clock_collector", "scripts/tracing/clock_bridge_collector.py"),
        ("successor_collector", "scripts/tracing/successor_lifecycle_monitor.py"),
        ("linearization_collector", "scripts/probes/c1_concurrency_monitor.py"),
        ("p5_collector", "scripts/probes/p5_runner.py"),
        ("route_oracle_0_4", "scripts/oracles/route_oracle_v0.py"),
        ("freshness_oracle_0_1", "scripts/oracles/pre_revocation_freshness_oracle.py"),
        ("successor_oracle_0_1", "scripts/oracles/successor_progression_oracle.py"),
        ("linearization_oracle_0_2", "scripts/oracles/authority_event_linearization_oracle.py"),
    ):
        binaries.append(_python_entry(component_id, source_path, implementation))
    binaries.append(
        _binary(
            component_id="n1_collector",
            source_commit=implementation,
            source_path="scripts/probes/run_n1_trajectory_residue.sh",
            build_target="shell_syntax_and_container_install",
            build_command="bash -n scripts/probes/run_n1_trajectory_residue.sh",
            build_flags=[],
            output_path=ROOT / "scripts/probes/run_n1_trajectory_residue.sh",
            binary_type="SHELL_ENTRY",
        )
    )
    inventory = {
        "schema_version": "1.0",
        "inventory_id": "FAMILY_A_FUZZER_V0_CONTAINER_PACKAGES",
        "image_id": image_id,
        "architecture": platform.machine(),
        "os_release": Path("/etc/os-release").read_text(encoding="utf-8"),
        "environment": {
            name: os.getenv(name)
            for name in (
                "ROS_DISTRO",
                "RMW_IMPLEMENTATION",
                "AMENT_PREFIX_PATH",
                "CMAKE_PREFIX_PATH",
                "COLCON_PREFIX_PATH",
                "PYTHONPATH",
            )
        },
        "identities": {
            "python": _run("python3", "--version"),
            "gcc": _run("gcc", "--version").splitlines()[0],
            "cmake": _run("cmake", "--version").splitlines()[0],
            "gazebo": _run("gz", "--versions"),
            "colcon": _run("colcon", "version-check", check=False),
            "ros2": _run("ros2", "--help").splitlines()[0],
        },
        "source_commits": {
            "repository_implementation": implementation,
            "PX4": px4_commit,
            "px4_msgs": _git_commit(WORKSPACE / "ros/src/px4_msgs"),
            "px4_ros2_interface_lib": interface_commit,
            "Micro_XRCE_DDS_Agent": agent_commit,
        },
        "dpkg_packages": [
            line.split("\t", 1)
            for line in (Path("/opt/family_a/build-inventory/dpkg-packages.tsv"))
            .read_text(encoding="utf-8")
            .splitlines()
            if "\t" in line
        ],
        "python_packages": json.loads(
            Path("/opt/family_a/build-inventory/python-packages.json").read_text(
                encoding="utf-8"
            )
        ),
        "colcon_packages": (
            Path("/opt/family_a/build-inventory/colcon-packages.tsv")
            .read_text(encoding="utf-8")
            .splitlines()
        ),
        "ros_packages": _run("ros2", "pkg", "list").splitlines(),
        "runtime_started": False,
    }
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "FAMILY_A_FUZZER_V0_FORMAL_BINARIES",
        "image_id": image_id,
        "binaries": binaries,
    }
    return inventory, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--package-inventory", type=Path, required=True)
    parser.add_argument("--binary-manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        inventory, manifest = capture(args.image_id)
        args.package_inventory.parent.mkdir(parents=True, exist_ok=True)
        args.binary_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.package_inventory.write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        args.binary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (CaptureError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "package_count": len(inventory["dpkg_packages"]),
                "binary_count": len(manifest["binaries"]),
                "runtime_started": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
