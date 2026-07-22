from __future__ import annotations

from pathlib import Path

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


def test_w1_ledger_is_empty_append_only_and_has_only_registered_classes() -> None:
    prereg = _yaml("preregistration.yaml")
    ledger = _yaml("attempt_ledger.yaml")
    assert ledger["attempts"] == []
    assert ledger["diagnostics"] == []
    assert ledger["append_only"] is True
    assert ledger["allowed_classifications"] == prereg["attempt_classification"][
        "allowed"
    ]
    assert sum(ledger["classification_counts"].values()) == 0


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
    assert phases["W1-C"]["status"] == "BLOCKED_PENDING_ACCEPTED_W1_B"
    assert phases["W1-D"]["status"] == "BLOCKED_PENDING_ACCEPTED_W1_C"
    assert phases["W1-E"]["conditional"] is True
    assert matrix["native_adapter_gate"]["native_spike_authorized"] is False
