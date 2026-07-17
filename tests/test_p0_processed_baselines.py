from __future__ import annotations

import json
from array import array
from pathlib import Path

from jsonschema import Draft202012Validator
from scripts.probes.p0_route_runner import _name, _versioned_topic


ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "data" / "processed" / "p0"
SCHEMA = json.loads((ROOT / "data" / "schemas" / "route_trace.schema.json").read_text())
SUPERSEDED = {
    "p0a_offboard_20260716": {"scenario": "offboard", "nav_states": {14, 5}},
    "p0b_external_mode_20260716": {"scenario": "external", "nav_states": {23, 5}},
    "p0c_mode_executor_20260716": {"scenario": "executor", "nav_states": {17, 23, 5}},
}
CURRENT = {
    "p0a_offboard_phase_a1_20260716T0710": {"scenario": "offboard", "nav_states": {14, 5}},
    "p0b_external_mode_phase_a1_20260716T0720": {"scenario": "external", "nav_states": {23, 5}},
    "p0c_executor_phase_a1_20260716T0730": {"scenario": "executor", "nav_states": {17, 23, 5}},
}
EXPECTED = SUPERSEDED | CURRENT


def test_p0_runner_handles_px4_message_versions_and_fixed_names() -> None:
    message_type = type("VersionedMessage", (), {"MESSAGE_VERSION": 4})
    assert _versioned_topic("/fmu/out/vehicle_status", message_type) == "/fmu/out/vehicle_status_v4"
    assert _name(array("B", b"Route Transition\0padding")) == "Route Transition"


def test_p0_summaries_have_route_and_provenance_evidence() -> None:
    assert {path.name for path in P0.iterdir() if path.is_dir()} == set(EXPECTED)
    for run_id, expected in EXPECTED.items():
        summary = json.loads((P0 / run_id / "route_summary.json").read_text())
        assert summary["baseline"]["status"] == "PASS"
        assert summary["baseline"]["scenario"] == expected["scenario"]
        assert expected["nav_states"] <= set(summary["nav_state_transitions"])
        assert summary["producer_consumer_evidence"]["producer_publish_events"] > 0
        assert summary["producer_consumer_evidence"]["px4_consume_events"] > 0
        assert summary["producer_consumer_evidence"]["domains_require_clock_bridge"] is True
        if run_id in CURRENT:
            assert summary["schema_version"] == "1.1"
            assert summary["execution_status"] == "PASS"
            assert summary["route_verdict"] == "UNKNOWN"
            assert summary["writer_attribution"]["status"] == "SEQUENCE_GAP"
            assert summary["writer_attribution"]["rate_gate_passed"] is True
            assert summary["writer_attribution"]["actual_rate_hz"] >= 100
            oracle = json.loads((P0 / run_id / "route_oracle.json").read_text())
            assert oracle["route_oracle_version"] == "0.1"
            assert oracle["status"] == "UNKNOWN"
        else:
            assert summary["superseded_measurement_v1"] is True
            assert summary["writer_attribution"]["status"] == "ATTRIBUTED"
        assert summary["writer_attribution"]["actuator_writers"] == ["control_allocator"]
        assert summary["writer_attribution"]["allocator_input_writers"] == ["mc_rate_control"]
        assert {"ulog_us", "ros_node_ns"} == set(summary["timestamp_domains"])
        assert summary["source_artifacts"]
        for artifact in summary["source_artifacts"]:
            assert len(artifact["sha256"]) == 64
            assert artifact["bytes"] > 0


def test_all_p0_trace_events_validate_and_remain_compact() -> None:
    validator = Draft202012Validator(SCHEMA)
    for run_id in EXPECTED:
        trace = P0 / run_id / "route_trace.jsonl"
        assert trace.stat().st_size < 10 * 1024 * 1024
        count = 0
        with trace.open(encoding="utf-8") as handle:
            for count, line in enumerate(handle, 1):
                validator.validate(json.loads(line))
        summary = json.loads((P0 / run_id / "route_summary.json").read_text())
        assert count == summary["trace_event_count"]
