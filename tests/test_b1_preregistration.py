import csv
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
B1 = ROOT / "experiments" / "motivation" / "b1_family_b"


def load_yaml(name: str):
    return yaml.safe_load((B1 / name).read_text(encoding="utf-8"))


def test_b1_yaml_documents_parse_and_share_identity():
    docs = [
        load_yaml("preregistration.yaml"),
        load_yaml("source_lock.yaml"),
        load_yaml("matrix.yaml"),
        load_yaml("attempt_ledger.yaml"),
    ]
    assert {doc["study_id"] for doc in docs} == {
        "b1_registered_controller_inventory_family_b_gate"
    }
    assert all(doc["schema_version"] == "1.0" for doc in docs)


def test_b1_phase_order_caps_and_gate_are_frozen():
    prereg = load_yaml("preregistration.yaml")
    matrix = load_yaml("matrix.yaml")
    assert matrix["execution_order"] == [
        "B1-A",
        "B1-B",
        "B1-C",
        "B1-D",
        "B1-E",
        "B1-F",
        "B1-G",
    ]
    assert prereg["formal_attempt_caps"]["B1-D"]["maximum_formal_attempts"] == 3
    assert prereg["formal_attempt_caps"]["B1-E"] == {
        "target_accepted": 3,
        "maximum_formal_attempts": 6,
    }
    assert prereg["formal_attempt_caps"]["B1-F"] == {
        "target_accepted": 3,
        "maximum_formal_attempts": 6,
    }
    assert len(prereg["reference_subject_authorization_gate"]["clauses"]) == 12


def test_b1_attempt_classifications_and_empty_ledger():
    prereg = load_yaml("preregistration.yaml")
    ledger = load_yaml("attempt_ledger.yaml")
    expected = {
        "ACCEPTED",
        "OBSERVABILITY_REJECTED",
        "MEASUREMENT_INSUFFICIENT",
        "ENVIRONMENT_FAILURE",
        "CAMPAIGN_CONFIGURATION_FAILURE",
        "FORMAL_SAFETY_STOP",
        "NOT_APPLICABLE",
    }
    assert set(prereg["attempt_classification"]["allowed"]) == expected
    assert set(ledger["allowed_classifications"]) == expected
    assert ledger["attempts"] == []


def test_b1_tsv_headers_and_enumerated_preregistration_states():
    expected_inventory_columns = {
        "subject_id",
        "registration_mechanism",
        "allocator_participation",
        "expected_authoritative_writer",
        "classification",
        "inclusion_decision",
    }
    with (B1 / "inventory.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert expected_inventory_columns <= set(rows[0])
    assert {row["classification"] for row in rows} == {"UNRESOLVED"}

    allowed_observability = {
        "DIRECTLY_OBSERVABLE",
        "DERIVABLE_WITH_COMPLETE_LINEAGE",
        "DERIVABLE_WITH_LIMITATION",
        "NOT_OBSERVABLE",
        "NOT_APPLICABLE",
    }
    with (B1 / "observability_matrix.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        observations = list(csv.DictReader(handle, delimiter="\t"))
    assert len(observations) >= 24
    assert {row["status"] for row in observations} <= allowed_observability


def test_b1_source_lock_uses_exact_commits_and_container_digest():
    lock = load_yaml("source_lock.yaml")
    assert lock["dependencies"]["px4_autopilot"]["commit"] == (
        "4ae21a5e569d3d89c2f6366688cbacb3e93437c9"
    )
    assert lock["dependencies"]["px4_msgs"]["commit"] == (
        "18ecff03041c6f8d8a0012fbc63af0b23dd60af1"
    )
    assert lock["dependencies"]["px4_ros2_interface_lib"]["commit"] == (
        "c3e410f035806e8c56246708432ded09c976434b"
    )
    assert lock["container"]["manifest_digest"].startswith("sha256:")
    assert len(lock["container"]["manifest_digest"]) == 71


def test_b1_json_outputs_parse_when_present():
    for relative in (
        B1 / "b1_gate.json",
        ROOT / "data" / "processed" / "motivation" / "b1_family_b" / "b1_summary.json",
    ):
        if relative.exists():
            json.loads(relative.read_text(encoding="utf-8"))
