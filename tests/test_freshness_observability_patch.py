from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from scripts.tracing.route_trace_collector import (
    SETPOINT_SOURCE,
    RouteEventReducer,
    lifecycle_events,
)


ROOT = Path(__file__).resolve().parents[1]
BASE_PATCH = ROOT / "patches" / "px4" / "route_observability" / "route_observability_topics.patch"
PATCH = ROOT / "patches" / "px4" / "route_observability" / "freshness_observability.patch"
LOGGER_PROFILE = ROOT / "config" / "freshness_logger_topics.txt"


def _additions(text: str) -> str:
    return "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def test_incremental_patch_is_controller_observation_only() -> None:
    text = PATCH.read_text(encoding="utf-8")
    changed = {line[6:] for line in text.splitlines() if line.startswith("+++ b/")}
    assert changed == {
        "msg/RouteObservability.msg",
        "src/modules/logger/logged_topics.cpp",
        "src/modules/mc_pos_control/MulticopterPositionControl.cpp",
        "src/modules/mc_att_control/mc_att_control.hpp",
        "src/modules/mc_att_control/mc_att_control_main.cpp",
        "src/modules/mc_rate_control/MulticopterRateControl.hpp",
        "src/modules/mc_rate_control/MulticopterRateControl.cpp",
    }
    additions = _additions(text)
    for required in (
        "SOURCE_EXTERNAL_ATTITUDE=12",
        "SOURCE_EXTERNAL_RATE=13",
        "EVENT_SETPOINT_CONSUMED",
        "_last_external_rates_setpoint",
        "_last_setpoint_observability_pub",
    ):
        assert required in additions
    for forbidden in (
        "timeout",
        "failsafe",
        "ScheduleOnInterval",
        "setAttitudeSetpoint(",
        "_rates_setpoint(0) =",
        "vehicle_torque_setpoint.xyz",
    ):
        assert forbidden not in additions


def test_collector_source_ids_match_incremental_patch() -> None:
    text = PATCH.read_text(encoding="utf-8")
    assert SETPOINT_SOURCE == {
        1: ("trajectory_setpoint", "velocity"),
        12: ("vehicle_attitude_setpoint", "attitude"),
        13: ("vehicle_rates_setpoint", "body_rate"),
    }
    assert "+uint8 SOURCE_EXTERNAL_ATTITUDE=12" in text
    assert "+uint8 SOURCE_EXTERNAL_RATE=13" in text


def test_freshness_logger_profile_contains_required_evidence() -> None:
    topics = {
        line.split()[0]
        for line in LOGGER_PROFILE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert {
        "route_observability",
        "arming_check_request",
        "arming_check_reply",
        "trajectory_setpoint",
        "vehicle_attitude_setpoint",
        "vehicle_rates_setpoint",
        "vehicle_torque_setpoint",
        "actuator_motors",
        "vehicle_angular_velocity",
        "vehicle_attitude",
        "vehicle_local_position",
        "vehicle_status",
    } <= topics


def test_attitude_and_rate_consumption_are_typed() -> None:
    reducer = RouteEventReducer("typed-consumption")
    attitude = reducer.reduce(
        "route_observability",
        {"event_type": 1, "source_id": 12, "subject_timestamp": 900_000},
        1_000_000,
    )
    assert attitude["event_type"] == "px4_setpoint_consumed"
    assert attitude["setpoint_topic"] == "vehicle_attitude_setpoint"
    assert attitude["setpoint_level"] == "attitude"
    rate = reducer.reduce(
        "route_observability",
        {"event_type": 1, "source_id": 13, "subject_timestamp": 900_000},
        1_100_000,
    )
    assert rate["setpoint_topic"] == "vehicle_rates_setpoint"
    assert rate["setpoint_level"] == "body_rate"


def test_freshness_lifecycle_uses_explicit_publish_clock(tmp_path: Path) -> None:
    lifecycle = tmp_path / "freshness.log"
    lifecycle.write_text(
        '[1700000000.000000000] [INFO] {"event_type":"freshness_mode_activated",'
        '"mode_id":23,"activation_id":1,"setpoint_type":"RATE"}\n'
        '[1700000000.100000000] [INFO] {"event_type":"freshness_setpoint_published",'
        '"sequence":4,"ros_time_ns":1700000000123456789,"activation_id":1,'
        '"setpoint_type":"RATE"}\n',
        encoding="utf-8",
    )
    events = list(lifecycle_events(lifecycle, "freshness-life"))
    assert events[0]["authority_source"] == "dynamic_external_mode"
    assert events[1]["event_type"] == "producer_still_publishing"
    assert events[1]["timestamp"] == 1_700_000_000_123_456_789
    assert events[1]["setpoint_topic"] == "vehicle_rates_setpoint"
    assert events[1]["producer_identity"] == "registered_component:Freshness Probe"


def test_patch_sequence_applies_to_locked_checkout() -> None:
    px4 = ROOT / "external" / "PX4-Autopilot"
    if not (px4 / ".git").exists():
        return
    temporary_root = Path(tempfile.mkdtemp(prefix="uav-sf-freshness-patch-"))
    worktree = temporary_root / "px4"
    commit = subprocess.check_output(
        ["git", "-C", str(px4), "rev-parse", "HEAD"], text=True
    ).strip()
    try:
        subprocess.run(
            ["git", "-C", str(px4), "worktree", "add", "--detach", str(worktree), commit],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["git", "-C", str(worktree), "apply", str(BASE_PATCH)], check=True)
        subprocess.run(
            ["git", "-C", str(worktree), "apply", "--check", str(PATCH)], check=True
        )
    finally:
        if worktree.exists():
            subprocess.run(
                ["git", "-C", str(px4), "worktree", "remove", str(worktree), "--force"],
                check=True,
            )
        temporary_root.rmdir()
