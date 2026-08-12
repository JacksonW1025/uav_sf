#!/usr/bin/env python3
"""Fail-closed checks for the canonical Thor experiment container."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


EXPECTED_PATHS = (
    Path("/opt/px4-venv/bin/python3"),
    Path("/opt/microxrce/bin/MicroXRCEAgent"),
    Path("/opt/family_a_ws/install/share/px4_msgs/package.xml"),
    Path("/opt/family_a_ws/install/share/px4_ros2_cpp/package.xml"),
    Path("/opt/family_a_ws/install/share/family_a_runtime/package.xml"),
    Path("/opt/family_a_ws/install/share/family_a_modes/package.xml"),
    Path("/opt/family_a_ws/install/lib/family_a_modes/gazebo_clock_sidecar"),
    Path("/opt/uav_sf/external/px4_autopilot/build/px4_sitl_default/bin/px4"),
    Path("/opt/family_a_candidate_manifest.json"),
)


def self_check() -> dict[str, Any]:
    os_release = platform.freedesktop_os_release()
    checks = {
        "architecture": platform.machine() == "aarch64",
        "operating_system": os_release.get("ID") == "ubuntu"
        and os_release.get("VERSION_CODENAME") == "noble",
        "python": sys.version_info[:2] == (3, 12)
        and "conda" not in sys.executable.lower()
        and sys.executable.startswith("/opt/px4-venv/"),
        "ros_distribution": os.environ.get("ROS_DISTRO") == "jazzy",
        "rmw": os.environ.get("RMW_IMPLEMENTATION") == "rmw_fastrtps_cpp",
        "candidate_paths": all(path.exists() for path in EXPECTED_PATHS),
        "host_python_absent": not any(
            value and ("miniconda" in value.lower() or "anaconda" in value.lower())
            for key, value in os.environ.items()
            if key in {"PATH", "PYTHONPATH", "CMAKE_PREFIX_PATH"}
        ),
        "host_gazebo_paths_absent": "/home/" not in os.environ.get(
            "GZ_SIM_RESOURCE_PATH", ""
        ),
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "python_executable": sys.executable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", required=True)
    parser.parse_args()
    result = self_check()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
