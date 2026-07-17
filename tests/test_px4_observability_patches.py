from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.tracing.route_trace_collector import WRITER_NAMES


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "px4" / "route_observability" / "route_observability_topics.patch"
CHECKER = ROOT / "scripts" / "setup" / "check_px4_observability_patch.py"
LOCK = ROOT / "config" / "dependencies.lock.yaml"
REBUILD = ROOT / "scripts" / "validation" / "rebuild_observability_patch.sh"


def load_checker():
    spec = importlib.util.spec_from_file_location("patch_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _new_file_text(patch_text: str, path: str) -> str:
    marker = f"diff --git a/{path} b/{path}\n"
    assert marker in patch_text
    section = patch_text.split(marker, 1)[1].split("\ndiff --git ", 1)[0]
    assert "new file mode" in section
    assert "--- /dev/null" in section
    assert f"+++ b/{path}" in section
    return "\n".join(
        line[1:]
        for line in section.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _constants(message: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in message.splitlines():
        if "=" in line and line.startswith("uint8 "):
            name, value = line.split(None, 1)[1].split("=", 1)
            result[name.strip()] = int(value)
    return result


def test_patch_is_self_contained_and_message_complete() -> None:
    text = PATCH.read_text(encoding="utf-8")
    message = _new_file_text(text, "msg/RouteObservability.msg")
    for field in (
        "timestamp",
        "subject_timestamp",
        "sequence",
        "expected_period_us",
        "route_epoch_id",
        "failed_check_mask",
        "component_hash",
        "event_type",
        "source_id",
        "topic_id",
        "writer_id",
        "profile",
        "instance",
        "previous_nav_state",
        "new_nav_state",
        "change_source",
        "registration_mode_id",
        "executor_in_charge",
        "arming_check_id",
        "result",
        "reason_code",
        "armed",
        "active_at_event",
        "fallback_nav_state",
    ):
        assert f" {field}" in message
    constants = _constants(message)
    assert constants["EVENT_SETPOINT_CONSUMED"] == 1
    assert constants["EVENT_ALLOCATOR_INPUT_PUBLISHED"] == 2
    assert constants["EVENT_ACTUATOR_OUTPUT_PUBLISHED"] == 3
    assert constants["EVENT_ROUTE_EPOCH_CHANGED"] == 4
    assert constants["EVENT_UNREGISTER_REQUEST_PROCESSED"] == 5
    assert constants["EVENT_ARMING_REQUEST_REJECTED"] == 9
    assert constants["EVENT_REGISTRATION_PROCESSED"] == 10
    assert constants["ORB_QUEUE_LENGTH"] == 4
    assert constants["WRITER_UNKNOWN"] == 0
    assert constants["WRITER_MC_RATE_CONTROL"] == 1
    assert constants["WRITER_CONTROL_ALLOCATOR"] == 2
    assert constants["WRITER_ROVER_ACKERMANN"] == 3
    assert constants["WRITER_ROVER_DIFFERENTIAL"] == 4
    assert constants["WRITER_ROVER_MECANUM"] == 5
    assert constants["PROFILE_BASELINE"] == 1
    assert constants["PROFILE_TRANSITION"] == 2
    assert "+\tRouteObservability.msg" in text


def test_patch_is_observation_only_and_scoped() -> None:
    text = PATCH.read_text(encoding="utf-8")
    assert "printf(" not in text
    changed = {
        line[6:]
        for line in text.splitlines()
        if line.startswith("+++ b/")
    }
    assert changed <= {
        "msg/CMakeLists.txt",
        "msg/RouteObservability.msg",
        "src/lib/route_observability/RouteObservability.hpp",
        "src/modules/commander/Commander.cpp",
        "src/modules/commander/Commander.hpp",
        "src/modules/commander/HealthAndArmingChecks/HealthAndArmingChecks.hpp",
        "src/modules/commander/ModeManagement.cpp",
        "src/modules/commander/ModeManagement.hpp",
        "src/modules/control_allocator/ControlAllocator.cpp",
        "src/modules/control_allocator/ControlAllocator.hpp",
        "src/modules/logger/logged_topics.cpp",
        "src/modules/mc_pos_control/MulticopterPositionControl.cpp",
        "src/modules/mc_pos_control/MulticopterPositionControl.hpp",
        "src/modules/mc_rate_control/MulticopterRateControl.cpp",
        "src/modules/mc_rate_control/MulticopterRateControl.hpp",
        "src/modules/rover_ackermann/AckermannActControl/AckermannActControl.cpp",
        "src/modules/rover_ackermann/AckermannActControl/AckermannActControl.hpp",
        "src/modules/rover_differential/DifferentialActControl/DifferentialActControl.cpp",
        "src/modules/rover_differential/DifferentialActControl/DifferentialActControl.hpp",
        "src/modules/rover_mecanum/MecanumActControl/MecanumActControl.cpp",
        "src/modules/rover_mecanum/MecanumActControl/MecanumActControl.hpp",
    }
    additions = "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for forbidden in (
        "actuator_motors.control[",
        "vehicle_control_mode.nav_state",
        "ScheduleOnInterval",
        "setControlAllocation",
        "trajectory_setpoint.position",
    ):
        assert forbidden not in additions


def test_collector_writer_ids_match_message_definition() -> None:
    message = _new_file_text(PATCH.read_text(encoding="utf-8"), "msg/RouteObservability.msg")
    constants = _constants(message)
    expected = {
        constants[name]: name.removeprefix("WRITER_").lower()
        for name in constants
        if name.startswith("WRITER_")
    }
    assert WRITER_NAMES == expected


def test_checker_reads_the_shared_dependency_lock() -> None:
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    assert load_checker().locked_commit() == lock["px4_autopilot"]["commit"]
    assert "LOCKED_COMMIT =" not in CHECKER.read_text(encoding="utf-8")
    assert REBUILD.stat().st_mode & 0o111


def test_patch_applies_to_locked_checkout() -> None:
    px4 = ROOT / "external" / "PX4-Autopilot"
    if not (px4 / ".git").exists():
        pytest.skip("ignored locked PX4 checkout not present")
    result = load_checker().check(px4)
    assert result["status"] == "APPLICABLE"
    subprocess.run(["git", "-C", str(px4), "apply", "--check", str(PATCH)], check=True)
