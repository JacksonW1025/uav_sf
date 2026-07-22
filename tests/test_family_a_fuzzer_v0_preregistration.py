import csv
import json
from pathlib import Path

import jsonschema
import yaml

from scripts.validation.check_family_a_fuzzer_v0_preregistration import validate


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/fuzzer_v0/family_a"


def load_yaml(name: str):
    return yaml.safe_load((BASE / name).read_text(encoding="utf-8"))


def test_complete_bundle_passes_consistency_checker():
    result = validate()
    assert result == {
        "seed_records": 61,
        "runtime_seeds": 50,
        "historical_replay_seeds": 1,
        "excluded_seeds": 10,
        "state_fields": 33,
        "event_edges": 26,
        "variation_operators": 27,
        "comparison_budget": 36,
        "formal_attempts": 0,
        "tracked_raw_files": 0,
        "oracle_identity_records": result["oracle_identity_records"],
    }
    assert result["oracle_identity_records"] >= 18


def test_seed_catalog_admits_only_accepted_current_family_a_runtime_rows():
    with (BASE / "seed_catalog.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    runtime = [row for row in rows if row["inclusion_status"] == "ACCEPTED_RUNTIME_SEED"]
    replay = [row for row in rows if row["inclusion_status"] == "ACCEPTED_REPLAY_BENCHMARK"]
    excluded = [row for row in rows if row["inclusion_status"] == "EXCLUDED"]
    assert (len(runtime), len(replay), len(excluded)) == (50, 1, 10)
    assert all(row["current_or_historical"] == "CURRENT" for row in runtime)
    assert all(row["runtime_or_replay"] == "RUNTIME" for row in runtime)
    assert replay[0]["seed_id"] == "ISSUE162_HISTORICAL_REPLAY"
    assert replay[0]["runtime_or_replay"] == "REPLAY_ONLY"
    assert {row["source_campaign"] for row in runtime}.isdisjoint({"R1", "W1", "B1", "ORACLE_VALIDATION"})


def test_state_and_reachable_grammar_are_frozen():
    state = load_yaml("state_model.yaml")
    events = load_yaml("event_grammar.yaml")
    mutations = load_yaml("mutation_grammar.yaml")
    assert len(state["state_fields"]) == 33
    assert set(state["command_age_buckets"]) >= {
        "FRESH", "RETAINED_SHORT", "RETAINED_MEDIUM", "RETAINED_LONG", "POST_REVOCATION", "UNKNOWN"
    }
    assert events["edge_count"] == len(events["edges"]) == 26
    assert events["composition_rules"]["maximum_authority_events_initial_v0"] == 2
    assert all(edge["source_state_predicate"] and edge["public_trigger"] and edge["provenance"] for edge in events["edges"])
    assert mutations["operator_count"] == len(mutations["operators"]) == 27
    assert mutations["conditionally_disabled"]["bounded_DDS_delay_drop_reorder"]["enabled"] is False
    operators = {operator["operator_id"]: operator for operator in mutations["operators"]}
    assert operators["TM_UPDATE_INTERVAL"]["parameter_domain"] == {"publication_interval_ms": [50]}
    assert operators["MC_BOUNDED_TURN"]["parameter_domain"]["turn_rate_rad_s"] == [0.15]
    assert mutations["conditionally_disabled"]["acceleration_and_braking_parameterization"]["enabled"] is False


def test_equal_budget_and_state_aware_selection_are_immutable():
    strategy = load_yaml("strategy_matrix.yaml")
    campaign = load_yaml("campaign_matrix.yaml")
    analysis = load_yaml("analysis_plan.yaml")
    assert strategy["equal_budget_assertions"]["budget_vector"] == [12, 12, 12]
    assert strategy["equal_budget_assertions"]["total_future_formal_runtime_budget"] == 36
    assert campaign["budget_rules"]["total_future_formal_comparison_attempts"] == 36
    assert campaign["budget_rules"]["current_task_formal_attempts"] == 0
    assert analysis["state_aware_selection"]["runtime_weight_or_priority_change"] == "forbidden"
    assert analysis["state_aware_selection"]["rejected_attempt_updates_coverage"] is False


def test_activation_gate_is_schema_valid_closed_and_zero_attempt():
    gate = json.loads((BASE / "activation_gate.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "data/schemas/family_a_fuzzer_v0_activation_gate.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(gate)
    assert gate["status"] == "PREREGISTERED_NOT_ACTIVATED"
    assert gate["campaign_activated"] is False
    assert gate["runtime_authorized"] is False
    assert gate["formal_attempts_authorized"] is False
    assert gate["activation_requires_separate_commit"] is True
    assert gate["activation_requires_explicit_review"] is True
    assert gate["consistency_check_passed"] is True
    assert gate["focused_tests_passed"] is True
    assert gate["validate_repo_passed"] is True

    ledger = load_yaml("attempt_ledger.yaml")
    assert ledger["activation_commit"] is None
    assert ledger["formal_attempts"] == 0
    assert set(ledger["strategy_counts"].values()) == {0}
    assert ledger["attempts"] == []


def test_oracle_semantics_do_not_collapse_evidence_classes():
    lock = load_yaml("oracle_lock.yaml")
    prereg = load_yaml("preregistration.yaml")
    assert lock["route_oracle"]["version"] == "0.4"
    assert lock["identity_consistency"]["old_Route_Oracle_0_3_identity_used"] is False
    assert lock["outcome_semantics"]["UNKNOWN_is_PASS"] is False
    assert lock["outcome_semantics"]["NOT_APPLICABLE_is_PASS"] is False
    assert lock["outcome_semantics"]["EXPOSURE_is_VIOLATION"] is False
    assert prereg["current_state"]["state_aware_search_gain_supported"] is False
    assert prereg["current_state"]["full_method_effectiveness_supported"] is False
