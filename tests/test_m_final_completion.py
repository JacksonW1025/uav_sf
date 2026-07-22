import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.validation.check_m_final_consistency import validate


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "experiments/motivation/m_final/motivation_completion_gate.json"
SCHEMA = ROOT / "data/schemas/motivation_completion_gate.schema.json"


def test_m_final_gate_schema_and_consistency():
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(gate)
    result = validate()
    assert result["evidence_units"] == 23
    assert result["tracked_raw_files"] == 0
    assert result["blocking_findings"] == 0


def test_m_final_authorization_is_preregistration_only():
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    assert gate["authorizes_fuzzer_v0_preregistration"] is True
    assert gate["authorizes_family_a_only"] is True
    assert gate["required_next_phase_preregistration"] is True
    assert gate["next_registered_phase"] == "FAMILY_A_FUZZER_V0_PREREGISTRATION"
    assert gate["authorized_empirical_family"] == ["Family_A"]
    for field in (
        "authorizes_real_workload_campaign",
        "authorizes_family_b_campaign",
        "authorizes_random_campaign",
        "authorizes_stateful_testing_full_campaign",
        "authorizes_hitl",
        "authorizes_real_flight",
    ):
        assert gate[field] is False


def test_m_final_limitations_are_not_promoted():
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    assert gate["mg7_status"] == "PARTIAL_PASS"
    assert gate["mg8_status"] == "MEASUREMENT_INSUFFICIENT"
    assert gate["mg9_status"] == "ENVIRONMENT_BLOCKED"
    assert gate["session_rollover_supported"] is False
    assert gate["real_workload_runtime_value_supported"] is False
    assert gate["family_b_runtime_generality_supported"] is False
    assert gate["current_natural_event_stable_reproduction_supported"] is False
    assert gate["state_aware_search_gain_supported"] is False
    assert gate["full_fuzzing_effectiveness_supported"] is False
