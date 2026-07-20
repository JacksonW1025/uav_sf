from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = (
    ROOT
    / "scripts/adapters/external_mode_adapter/include/freshness_probe_mode.hpp"
).read_text(encoding="utf-8")
SOURCE = (
    ROOT / "scripts/adapters/external_mode_adapter/src/freshness_probe.cpp"
).read_text(encoding="utf-8")
CMAKE = (
    ROOT / "scripts/adapters/external_mode_adapter/CMakeLists.txt"
).read_text(encoding="utf-8")


def test_one_lifecycle_supports_all_formal_setpoint_levels() -> None:
    assert "TrajectorySetpointType" in HEADER
    assert "AttitudeSetpointType" in HEADER
    assert "RatesSetpointType" in HEADER
    assert 'UAV_SF_SETPOINT_TYPE' in HEADER
    assert '"TRAJECTORY"' in HEADER
    assert '"ATTITUDE"' in HEADER
    assert '"RATE"' in HEADER


def test_setpoint_and_health_channels_are_independent() -> None:
    assert 'channelEnabled("setpoint.off")' in HEADER
    assert 'channelEnabled("health_reply.off")' in HEADER
    assert "setArmingCheckReplyEnabled(health_enabled)" in HEADER
    assert "if (!setpoint_enabled)" in HEADER
    assert "checkArmingAndRunConditions" in HEADER


def test_harness_emits_required_producer_and_health_markers() -> None:
    for event_type in (
        "freshness_mode_registered",
        "freshness_mode_activated",
        "freshness_setpoint_published",
        "freshness_health_reply",
        "freshness_channel_state",
        "freshness_mode_deactivated",
    ):
        assert event_type in HEADER + SOURCE
    assert "last_publish_ros_ns" in HEADER
    assert "publish_sequence_" in HEADER


def test_freshness_target_is_built_and_installed() -> None:
    assert "add_executable(external_mode_freshness_probe" in CMAKE
    assert "external_mode_freshness_probe" in CMAKE


def test_harness_is_non_replacement_dynamic_external_mode() -> None:
    assert 'Settings{"Freshness Probe"}.preventArming(false)' in HEADER
    assert "replaceInternalMode" not in HEADER
