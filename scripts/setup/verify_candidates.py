#!/usr/bin/env python3
"""Verify and hash the candidate binaries built for the Thor runtime image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


class CandidateError(RuntimeError):
    """A built candidate is absent or has the wrong platform identity."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _file_identity(path: Path) -> str:
    result = subprocess.run(
        ["file", "--brief", str(path)], check=True, text=True, capture_output=True
    )
    identity = result.stdout.strip()
    if "ARM aarch64" not in identity and "ARM64" not in identity:
        raise CandidateError(f"candidate is not an aarch64 binary: {path}: {identity}")
    return identity


def _command_identity(*command: str) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or not output:
        raise CandidateError(f"version command failed: {' '.join(command)}")
    return output


def _git_identity(path: Path) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(path), *arguments],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    # Porcelain's two status columns are positional.  Do not pass this output
    # through ``strip()`` or the leading worktree-status space will disappear
    # and the first byte of the path will be misreported.
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    submodules = git("submodule", "status", "--recursive").splitlines()
    return {
        "commit": git("rev-parse", "HEAD"),
        "changed_paths": sorted(
            line[3:].split(" -> ", 1)[-1]
            for line in status.splitlines()
            if len(line) > 3 and not line[3:].startswith(("build-", "install-"))
        ),
        "submodules": submodules,
    }


def build_manifest(
    *, px4_binary: Path, agent_binary: Path, workspace_prefix: Path
) -> dict[str, Any]:
    if platform.machine() != "aarch64":
        raise CandidateError("candidate verification requires native aarch64")
    for path in (px4_binary, agent_binary, workspace_prefix):
        if not path.exists():
            raise CandidateError(f"candidate path is missing: {path}")
    package_markers = {
        "px4_msgs": workspace_prefix / "share/px4_msgs/package.xml",
        "px4_ros2_cpp": workspace_prefix / "share/px4_ros2_cpp/package.xml",
        "family_a_runtime": workspace_prefix / "share/family_a_runtime/package.xml",
        "family_a_modes": workspace_prefix / "share/family_a_modes/package.xml",
    }
    missing = [name for name, path in package_markers.items() if not path.is_file()]
    if missing:
        raise CandidateError("workspace packages are missing: " + ", ".join(missing))
    installed_locks = {
        "installed_deb": Path("/opt/family_a_installed_deb_packages.lock"),
        "installed_python": Path("/opt/family_a_installed_python_packages.lock"),
    }
    absent_locks = [name for name, path in installed_locks.items() if not path.is_file()]
    if absent_locks:
        raise CandidateError("installed package closures are missing: " + ", ".join(absent_locks))
    sources = {
        "PX4-Autopilot": ROOT / "external/px4_autopilot",
        "px4_msgs": ROOT / "external/px4_msgs",
        "px4_ros2_interface_lib": ROOT / "external/px4_ros2_interface_lib",
        "Micro-XRCE-DDS-Agent": ROOT / "external/micro_xrce_dds_agent",
    }
    project_binaries = {
        "external_mode": workspace_prefix / "lib/family_a_modes/external_mode",
        "mode_executor": workspace_prefix / "lib/family_a_modes/mode_executor",
        "gazebo_clock_sidecar": workspace_prefix
        / "lib/family_a_modes/gazebo_clock_sidecar",
    }
    missing_project_binaries = [
        name for name, path in project_binaries.items() if not path.is_file()
    ]
    if missing_project_binaries:
        raise CandidateError(
            "project binaries are missing: " + ", ".join(missing_project_binaries)
        )
    revision_path = Path("/opt/family_a_repository_revision")
    if not revision_path.is_file():
        raise CandidateError("repository revision record is missing")
    return {
        "schema_version": "1.0",
        "architecture": platform.machine(),
        "operating_system": platform.freedesktop_os_release().get("PRETTY_NAME", "unknown"),
        "python": platform.python_version(),
        "ros_distribution": os.environ.get("ROS_DISTRO"),
        "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION"),
        "repository_revision": revision_path.read_text(encoding="utf-8").strip(),
        "gazebo_sim_version": _command_identity("gz", "sim", "--versions"),
        "binaries": {
            "px4_sitl": {
                "path": str(px4_binary),
                "sha256": _sha256(px4_binary),
                "file_identity": _file_identity(px4_binary),
            },
            "micro_xrce_dds_agent": {
                "path": str(agent_binary),
                "sha256": _sha256(agent_binary),
                "file_identity": _file_identity(agent_binary),
                "logger_profile": False,
                "p2p_profile": False,
            },
            **{
                name: {
                    "path": str(path),
                    "sha256": _sha256(path),
                    "file_identity": _file_identity(path),
                }
                for name, path in project_binaries.items()
            },
        },
        "source_trees": {name: _git_identity(path) for name, path in sources.items()},
        "locks": {
            "dependencies": _sha256(ROOT / "config/dependencies.lock.json"),
            "patches": _sha256(ROOT / "config/patches.lock.json"),
            "runtime_apt": _sha256(
                ROOT / "containers/family_a_runtime/runtime-apt-packages.lock"
            ),
            "runtime_ros": _sha256(
                ROOT / "containers/family_a_runtime/runtime-ros-packages.lock"
            ),
            "runtime_python": _sha256(
                ROOT / "containers/family_a_runtime/python-packages.lock"
            ),
            **{name: _sha256(path) for name, path in installed_locks.items()},
        },
        "workspace_packages": sorted(package_markers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--px4-binary", type=Path, required=True)
    parser.add_argument("--agent-binary", type=Path, required=True)
    parser.add_argument("--workspace-prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        manifest = build_manifest(
            px4_binary=arguments.px4_binary,
            agent_binary=arguments.agent_binary,
            workspace_prefix=arguments.workspace_prefix,
        )
        if arguments.output.exists():
            raise CandidateError(f"refusing to overwrite manifest: {arguments.output}")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (CandidateError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}))
        return 1
    print(json.dumps({"status": "PASS", "output": str(arguments.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
