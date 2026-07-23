import csv
import json
from pathlib import Path

import jsonschema
import yaml

from scripts.validation.check_family_a_fuzzer_v0_activation_review import validate


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "experiments/fuzzer_v0/family_a/activation_review"


def load_yaml(name: str):
    return yaml.safe_load((REVIEW / name).read_text(encoding="utf-8"))


def load_decision():
    return json.loads(
        (REVIEW / "qualification_activation_decision.json").read_text(encoding="utf-8")
    )


def test_activation_review_bundle_passes_consistency_checker():
    result = validate()
    assert result["blocking_failures"] == 11
    assert result["non_blocking_findings"] == 4
    assert result["seed_records"] == 61
    assert result["runtime_seeds"] == 50
    assert result["historical_replay_seeds"] == 1
    assert result["excluded_seeds"] == 10
    assert result["unresolved_seeds"] == 0
    assert result["qualification_formal_attempts"] == 0
    assert result["comparison_attempts"] == 0
    assert result["tracked_raw_files"] == 0


def test_decline_decision_is_schema_valid_and_authorizes_no_runtime():
    decision = load_decision()
    schema = json.loads(
        (
            ROOT
            / "data/schemas/family_a_fuzzer_v0_qualification_activation.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(decision)
    assert decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
    assert decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
    assert decision["authorized_scope"] == "NONE"
    assert decision["qualification_authorized"] is False
    assert decision["runtime_authorized"] is False
    authorization_fields = [
        name for name in decision if name.endswith("_authorized")
    ]
    assert authorization_fields
    assert all(decision[name] is False for name in authorization_fields)


def test_checklist_has_exact_status_vocabulary_and_matching_blockers():
    with (REVIEW / "activation_review_checklist.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    decision = load_decision()
    assert {row["status"] for row in rows} <= {
        "PASS",
        "FAIL",
        "NOT_APPLICABLE",
    }
    blockers = [
        row["clause_id"]
        for row in rows
        if row["blocking"] == "true" and row["status"] == "FAIL"
    ]
    assert blockers == decision["blocking_clauses"]
    assert len(blockers) == decision["blocking_clause_count"] == 11


def test_qualification_ledger_is_not_authorized_and_empty():
    ledger = load_yaml("qualification_attempt_ledger.yaml")
    assert ledger["campaign_id"] == "FAMILY_A_FUZZER_V0"
    assert ledger["phase_id"] == "V0_P_QUALIFICATION"
    assert ledger["status"] == "NOT_AUTHORIZED"
    assert ledger["formal_attempts"] == 0
    assert ledger["accepted_attempts"] == 0
    assert ledger["comparison_attempts"] == 0
    assert ledger["next_attempt_id"] == "V0P-A1"
    assert ledger["runtime_executed"] is False
    assert ledger["attempts"] == []


def test_runbook_freezes_future_slots_without_executable_entry():
    text = (REVIEW / "qualification_runbook.md").read_text(encoding="utf-8")
    assert "REQUIRED_FUTURE_ENTRY" in text
    assert "NOT EXECUTABLE AT THIS REVIEW COMMIT" in text
    assert "stop" in text.lower()
    assert "three accepted" in text.lower()
    assert "slot six" in text.lower()
    assert "comparison" in text.lower()
    assert not (ROOT / "scripts/fuzzer/family_a_qualification_runner.py").exists()
    assert not (ROOT / "scripts/fuzzer/family_a_qualification_ledger.py").exists()


def test_original_preregistration_gate_remains_closed_and_unchanged_in_semantics():
    gate = json.loads(
        (
            ROOT / "experiments/fuzzer_v0/family_a/activation_gate.json"
        ).read_text(encoding="utf-8")
    )
    prereg = yaml.safe_load(
        (
            ROOT / "experiments/fuzzer_v0/family_a/preregistration.yaml"
        ).read_text(encoding="utf-8")
    )
    assert gate["status"] == "PREREGISTERED_NOT_ACTIVATED"
    assert gate["campaign_activated"] is False
    assert gate["runtime_authorized"] is False
    assert gate["formal_attempts_authorized"] is False
    assert prereg["current_state"]["formal_attempts"] == 0
    assert prereg["current_state"]["state_aware_search_gain_supported"] is False
    assert prereg["current_state"]["full_method_effectiveness_supported"] is False
