from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "px4" / "route_observability" / "route_observability_topics.patch"
CHECKER = ROOT / "scripts" / "setup" / "check_px4_observability_patch.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("patch_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patch_is_observation_only_and_scoped() -> None:
    text = PATCH.read_text(encoding="utf-8")
    assert "RouteObservability.msg" in text
    assert "EVENT_SETPOINT_CONSUMED" in text
    assert "WRITER_CONTROL_ALLOCATOR" in text
    assert "printf(" not in text
    changed = {
        line[6:]
        for line in text.splitlines()
        if line.startswith("+++ b/")
    }
    assert changed <= {
        "msg/CMakeLists.txt",
        "msg/RouteObservability.msg",
        "src/modules/control_allocator/ControlAllocator.cpp",
        "src/modules/control_allocator/ControlAllocator.hpp",
        "src/modules/logger/logged_topics.cpp",
        "src/modules/mc_pos_control/MulticopterPositionControl.cpp",
        "src/modules/mc_pos_control/MulticopterPositionControl.hpp",
        "src/modules/mc_rate_control/MulticopterRateControl.cpp",
        "src/modules/mc_rate_control/MulticopterRateControl.hpp",
    }


def test_patch_applies_to_locked_checkout() -> None:
    px4 = ROOT / "external" / "PX4-Autopilot"
    if not (px4 / ".git").exists():
        pytest.skip("ignored locked PX4 checkout not present")
    result = load_checker().check(px4)
    assert result["status"] == "APPLICABLE"
    subprocess.run(["git", "-C", str(px4), "apply", "--check", str(PATCH)], check=True)
