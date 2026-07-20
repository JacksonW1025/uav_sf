from __future__ import annotations

import math
from pathlib import Path

from scripts.analysis.summarize_freshness_run import (
    _baseline_complete,
    _health_evidence,
    _physical_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/probes/run_freshness_scenario.sh"
MONITOR = ROOT / "scripts/probes/freshness_flight_monitor.py"
INJECTOR = ROOT / "scripts/probes/inject_freshness_fault.py"
AGENT_BUILDER = ROOT / "scripts/setup/build_freshness_agent.sh"


def test_runner_keeps_attempts_immutable_and_uses_locked_local_agent() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "refusing to overwrite existing raw attempt" in text
    assert "runs/freshness_agent_build" in text
    assert "freshness_logger_topics.txt" in text
    assert "PX4_PARAM_SDLOG_PROFILE=0" in text
    assert "route_oracle_v0.py" in text
    assert "pre_revocation_freshness_oracle.py" in text


def test_fault_channels_are_independent_and_total_stop_is_sigkill() -> None:
    injector = INJECTOR.read_text(encoding="utf-8")
    monitor = MONITOR.read_text(encoding="utf-8")
    assert 'os.kill(args.pid, signal.SIGKILL)' in injector
    assert '(args.control_dir / "setpoint.off").touch(exist_ok=False)' in injector
    assert 'args.fault_type == "SETPOINT_ONLY_STALL"' in monitor
    assert '"REQUEST_HOLD"' in monitor
    assert 'telemetry_counts["angular_velocity"] >= 20' not in monitor


def test_agent_builder_reads_lock_and_does_not_modify_source() -> None:
    text = AGENT_BUILDER.read_text(encoding="utf-8")
    assert "verify_dependency_lock.py" in text
    assert "micro_xrce_dds_agent.commit" in text
    assert "UAGENT_SUPERBUILD=ON" in text
    assert 'status --porcelain' in text


def test_health_coverage_and_loss_detection_are_distinct() -> None:
    requests = [
        {"timestamp": 1_100_000, "request_id": 2, "valid_registrations_mask": 1},
        {"timestamp": 1_400_000, "request_id": 3, "valid_registrations_mask": 1},
        {"timestamp": 1_700_000, "request_id": 4, "valid_registrations_mask": 0},
    ]
    replies = [
        {"timestamp": 900_000, "request_id": 1, "registration_id": 0},
        {"timestamp": 1_110_000, "request_id": 2, "registration_id": 0},
        {"timestamp": 1_410_000, "request_id": 3, "registration_id": 0},
    ]
    result = _health_evidence(requests, replies, 1_000_000, 1_800_000)
    assert result["health_loss_detection_us"] == 1_700_000
    assert result["matched_reply_count"] == 2
    assert result["alive_through_target"] is False


def test_physical_metrics_use_fault_relative_position_and_absolute_tilt() -> None:
    half_angle = math.radians(20) / 2
    positions = [
        {"timestamp": 900_000, "x": 1.0, "y": 2.0, "z": -3.0},
        {"timestamp": 1_100_000, "x": 4.0, "y": 6.0, "z": -2.5},
    ]
    attitudes = [
        {
            "timestamp": 1_050_000,
            "q[0]": math.cos(half_angle),
            "q[1]": math.sin(half_angle),
            "q[2]": 0.0,
            "q[3]": 0.0,
        }
    ]
    rates = [
        {"timestamp": 1_060_000, "xyz[0]": 0.3, "xyz[1]": 0.4, "xyz[2]": 0.0}
    ]
    result = _physical_metrics(positions, attitudes, rates, 1_000_000, 1_200_000)
    assert result["altitude_loss_m"] == 0.5
    assert result["horizontal_displacement_m"] == 5.0
    assert math.isclose(float(result["maximum_attitude_excursion_deg"]), 20.0)
    assert result["maximum_angular_rate_excursion_rad_s"] == 0.5


def test_baseline_gate_is_setpoint_specific() -> None:
    common = {
        "position_samples": 40,
        "attitude_samples": 40,
        "angular_rate_samples": 40,
        "altitude_span_m": 0.1,
        "median_horizontal_speed_m_s": 0.4,
        "median_roll_rad": 0.1,
        "median_roll_rate_rad_s": 0.08,
    }
    for setpoint_type in ("TRAJECTORY", "ATTITUDE", "RATE"):
        assert _baseline_complete(common, setpoint_type, {}) == (True, [])
