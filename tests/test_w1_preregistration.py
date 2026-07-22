from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]
W1 = ROOT / "experiments/motivation/w1_workload"


def _yaml(name: str) -> dict:
    return yaml.safe_load((W1 / name).read_text(encoding="utf-8"))


def test_w1_preregistration_freezes_workload_sequence_caps_and_dispositions() -> None:
    prereg = _yaml("preregistration.yaml")
    assert prereg["primary_workload"]["exact_commit"] == (
        "a8e7318b8d1d7c5adc580e8a16374357773bc11a"
    )
    assert prereg["low_risk_mission"]["sequence"] == [
        "internal_ground",
        "arm",
        "internal_takeoff",
        "Aerostack2_Offboard",
        "go_to",
        "follow_path",
        "cancel_to_hover",
        "explicit_aircraft_Land",
        "disarm",
    ]
    assert prereg["formal_runtime_caps"]["W1-B"] == {
        "target_accepted": 1,
        "maximum_formal_attempts": 3,
    }
    assert prereg["formal_runtime_caps"]["W1-C"] == {
        "target_accepted": 1,
        "maximum_formal_attempts": 3,
    }
    assert prereg["formal_runtime_caps"]["W1-D"] == {
        "target_accepted": 3,
        "maximum_formal_attempts": 6,
    }
    assert set(prereg["final_dispositions"]["values"]) == {
        "PASS_REAL_WORKLOAD_ADDS_NEW_ROUTE_OR_LIFECYCLE_SEMANTICS",
        "CONDITIONAL_PASS_REAL_WORKLOAD_ADDS_TRACE_OR_TIMING_VALUE",
        "NEGATIVE_SCOPE_DECISION_NO_ADDITIONAL_ROUTE_SEMANTICS",
        "MEASUREMENT_INSUFFICIENT",
        "ENVIRONMENT_BLOCKED",
    }


def test_w1_ledger_is_append_only_and_counts_registered_attempt_classes() -> None:
    prereg = _yaml("preregistration.yaml")
    ledger = _yaml("attempt_ledger.yaml")
    assert ledger["diagnostics"]
    assert all(item["formal_runtime"] is False for item in ledger["diagnostics"])
    assert ledger["append_only"] is True
    assert ledger["allowed_classifications"] == prereg["attempt_classification"][
        "allowed"
    ]
    attempt_count = sum(item["attempts"] for item in ledger["formal_attempt_counts"].values())
    assert len(ledger["attempts"]) == attempt_count
    assert sum(ledger["classification_counts"].values()) == attempt_count
    assert all(
        item["classification"] in ledger["allowed_classifications"]
        for item in ledger["attempts"]
    )


def test_w1_source_lock_pins_runtime_and_container_identity() -> None:
    lock = _yaml("source_lock.yaml")
    assert lock["workload"]["aerostack2"]["commit"] == (
        "a8e7318b8d1d7c5adc580e8a16374357773bc11a"
    )
    assert lock["flight_stack"]["px4_autopilot"]["commit"] == (
        "4ae21a5e569d3d89c2f6366688cbacb3e93437c9"
    )
    assert lock["runtime_environment"]["dds"]["implementation"] == (
        "rmw_fastrtps_cpp"
    )
    digest = lock["container"]["manifest_digest"]
    assert digest.startswith("sha256:") and len(digest) == 71
    assert lock["external_source_storage"]["large_dependencies_are_not_vendored"]


def test_w1_matrix_enforces_phase_order_and_native_gate() -> None:
    matrix = _yaml("matrix.yaml")
    assert matrix["execution_order"] == ["W1-A", "W1-B", "W1-C", "W1-D", "W1-E", "W1-F"]
    phases = {phase["phase_id"]: phase for phase in matrix["phases"]}
    assert phases["W1-B"]["status"] == "COMPLETE_CAP_REACHED_MEASUREMENT_INSUFFICIENT"
    assert phases["W1-C"]["status"] == "NOT_APPLICABLE_NO_ACCEPTED_W1_B_SOURCE_TRACE"
    assert phases["W1-D"]["status"] == "NOT_APPLICABLE_NO_ACCEPTED_W1_C_TRACE_ONLY_REPLAY"
    assert phases["W1-E"]["conditional"] is True
    assert matrix["native_adapter_gate"]["native_spike_authorized"] is False


def test_w1_final_gate_and_unavailable_trace_manifest_validate() -> None:
    for instance_name, schema_name in (
        ("w1_gate.json", "w1_gate.schema.json"),
        ("trace_manifest.json", "w1_trace_manifest.schema.json"),
    ):
        instance = json.loads((W1 / instance_name).read_text(encoding="utf-8"))
        schema = json.loads(
            (ROOT / "data" / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        jsonschema.validate(instance=instance, schema=schema)

    gate = json.loads((W1 / "w1_gate.json").read_text(encoding="utf-8"))
    assert gate["disposition"] == "MEASUREMENT_INSUFFICIENT"
    assert gate["canonical_attempts"] == 0
    assert gate["native_attempts"] == 0
    assert gate["authorizes_random_campaign"] is False
