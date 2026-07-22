from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.analysis.summarize_b1_reference_run import reference_lifecycle_records


ROOT = Path(__file__).resolve().parents[1]
B1 = ROOT / "experiments" / "motivation" / "b1_family_b"
HEADER = ROOT / "scripts" / "adapters" / "external_mode_adapter" / "include" / "b1_reference_controller.hpp"
RUNNER = ROOT / "scripts" / "probes" / "run_b1_reference_scenario.sh"
LOGGER = ROOT / "config" / "b1_reference_logger_topics.txt"


def test_reference_gate_has_all_authorization_clauses() -> None:
    decision = yaml.safe_load((B1 / "reference_decision.yaml").read_text(encoding="utf-8"))
    assert decision["reference_controller_authorized"] is True
    assert decision["runtime_probe_authorized"] is True
    assert decision["selected_classification"] == "PARTIAL_CONTROLLER_SUBGRAPH_REPLACEMENT"
    assert len(decision["authorization_clauses"]) == 12
    assert all(item["satisfied"] for item in decision["authorization_clauses"].values())


def test_reference_controller_is_bounded_and_not_a_classic_forwarder() -> None:
    text = HEADER.read_text(encoding="utf-8")
    assert "OdometryLocalPosition" in text
    assert "AttitudeSetpointType" in text
    assert "kMinimumThrust = 0.35f" in text
    assert "kMaximumThrust = 0.65f" in text
    assert "std::clamp" in text
    assert "std::isfinite" in text
    for forbidden in (
        "TrajectorySetpointType",
        "DirectActuatorsSetpointType",
        "ActuatorMotors",
        "random",
        "policy",
        "model",
    ):
        assert forbidden not in text


def test_reference_lifecycle_records_preserve_controller_identity(tmp_path: Path) -> None:
    lifecycle = tmp_path / "reference.log"
    lifecycle.write_text(
        '[1700000000.000000000] [INFO] {"event_type":"b1_reference_registered",'
        '"component_name":"B1 Reference","mode_id":23,"registration_instance_id":99,'
        '"setpoint_type":"ATTITUDE"}\n'
        '[1700000000.100000000] [INFO] {"event_type":"b1_reference_activated",'
        '"component_name":"B1 Reference","mode_id":23,"registration_instance_id":99,'
        '"activation_id":1}\n'
        '[1700000000.200000000] [INFO] {"event_type":"b1_reference_output",'
        '"component_name":"B1 Reference","mode_id":23,"registration_instance_id":99,'
        '"activation_id":1,"sequence":5,"ros_time_ns":1700000000200000000}\n',
        encoding="utf-8",
    )
    events = reference_lifecycle_records(lifecycle)
    assert events[0]["registration_instance_id"] == 99
    assert events[1]["activation_id"] == 1
    assert events[2]["event_type"] == "b1_reference_output"
    assert events[2]["component_name"] == "B1 Reference"


def test_b1_logger_and_runner_capture_required_graph_evidence() -> None:
    topics = {
        line.split()[0]
        for line in LOGGER.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert {
        "register_ext_component_request",
        "register_ext_component_reply",
        "setpoint_config",
        "vehicle_control_mode",
        "vehicle_attitude_setpoint",
        "vehicle_torque_setpoint",
        "actuator_motors",
        "route_observability",
    } <= topics
    runner = RUNNER.read_text(encoding="utf-8")
    assert "refusing to overwrite B1 attempt" in runner
    assert "MIS_TAKEOFF_ALT 1.5" in runner
    assert "b1_controlled_stop.py" in runner
    assert "route_oracle_v0.py" in runner


def test_b1_summarizer_rejects_missing_lineage(tmp_path: Path) -> None:
    result = {
        "schema_version": "1.0",
        "run_id": "placeholder",
        "checks": {"writer": False},
        "status": "MEASUREMENT_INSUFFICIENT",
    }
    encoded = json.dumps(result)
    assert "MEASUREMENT_INSUFFICIENT" in encoded
    assert "ACCEPTED" not in encoded


def test_b1_final_gate_preserves_build_failures_and_runtime_non_applicability() -> None:
    gate = json.loads((B1 / "b1_gate.json").read_text(encoding="utf-8"))
    ledger = yaml.safe_load((B1 / "attempt_ledger.yaml").read_text(encoding="utf-8"))
    assert gate["disposition"] == "ENVIRONMENT_BLOCKED"
    assert gate["static_build_attempts"] == 3
    assert gate["static_build_success"] is False
    assert gate["normal_attempts"] == gate["normal_accepted"] == 0
    assert gate["recovery_attempts"] == gate["recovery_accepted"] == 0
    assert gate["authorizes_family_b_full_campaign"] is False
    assert gate["authorizes_random_campaign"] is False
    assert gate["authorizes_stateful_testing"] is False
    assert gate["authorizes_m_final"] is True
    formal_builds = [
        attempt
        for attempt in ledger["attempts"]
        if attempt["phase"] == "B1-D" and attempt["formal_attempt"]
    ]
    assert len(formal_builds) == 3
    assert all(
        attempt["classification"] == "CAMPAIGN_CONFIGURATION_FAILURE"
        for attempt in formal_builds
    )
    assert {
        attempt["phase"]: attempt["classification"]
        for attempt in ledger["attempts"]
        if attempt["phase"] in {"B1-E", "B1-F"}
    } == {"B1-E": "NOT_APPLICABLE", "B1-F": "NOT_APPLICABLE"}
