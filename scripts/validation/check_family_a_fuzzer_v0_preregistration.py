#!/usr/bin/env python3
"""Validate the frozen, non-activated Family A Fuzzer v0 preregistration."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/fuzzer_v0/family_a"
ACTIVATION_SCHEMA = ROOT / "data/schemas/family_a_fuzzer_v0_activation_gate.schema.json"


def read_yaml(name: str) -> dict[str, Any]:
    value = yaml.safe_load((BASE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict), name
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def read_seeds() -> list[dict[str, str]]:
    with (BASE / "seed_catalog.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows
    return rows


def assert_ancestor(commit: str) -> None:
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iter_identity_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value
        for child in value.values():
            yield from iter_identity_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_identity_records(child)


def validate() -> dict[str, int]:
    required_assets = {
        "README.md",
        "activation_gate.json",
        "analysis_plan.yaml",
        "attempt_ledger.yaml",
        "campaign_matrix.yaml",
        "event_grammar.yaml",
        "evidence_rules.yaml",
        "final_adjudication_template.yaml",
        "mutation_grammar.yaml",
        "oracle_lock.yaml",
        "preregistration.yaml",
        "safety_rules.yaml",
        "seed_catalog.tsv",
        "source_lock.yaml",
        "state_model.yaml",
        "strategy_matrix.yaml",
    }
    assert required_assets <= {path.name for path in BASE.iterdir() if path.is_file()}

    prereg = read_yaml("preregistration.yaml")
    source_lock = read_yaml("source_lock.yaml")
    seeds = read_seeds()
    state = read_yaml("state_model.yaml")
    events = read_yaml("event_grammar.yaml")
    mutations = read_yaml("mutation_grammar.yaml")
    strategies = read_yaml("strategy_matrix.yaml")
    campaign = read_yaml("campaign_matrix.yaml")
    oracle_lock = read_yaml("oracle_lock.yaml")
    evidence = read_yaml("evidence_rules.yaml")
    safety = read_yaml("safety_rules.yaml")
    analysis = read_yaml("analysis_plan.yaml")
    ledger = read_yaml("attempt_ledger.yaml")
    activation = read_json(BASE / "activation_gate.json")

    # M-FINAL authorization is preregistration-only and Family A only.
    m_final = read_json(ROOT / "experiments/motivation/m_final/motivation_completion_gate.json")
    assert m_final["status"] == "CONDITIONALLY_COMPLETE"
    assert m_final["authorizes_fuzzer_v0_preregistration"] is True
    assert m_final["authorizes_family_a_only"] is True
    assert m_final["authorized_empirical_family"] == ["Family_A"]
    assert m_final["authorizes_random_campaign"] is False
    assert m_final["authorizes_stateful_testing_full_campaign"] is False
    assert m_final["state_aware_search_gain_supported"] is False
    assert m_final["full_fuzzing_effectiveness_supported"] is False
    assert prereg["m_final_disposition"] == m_final["disposition"]
    assert source_lock["authorization"] == {
        "M_FINAL_gate": "experiments/motivation/m_final/motivation_completion_gate.json",
        "authorizes_preregistration": True,
        "authorizes_family_a_only": True,
        "authorizes_runtime": False,
        "authorizes_random_campaign": False,
        "authorizes_full_stateful_campaign": False,
    }
    assert source_lock["starting_commit"] == "38725e87d8d0ebe03b1fe1712055725338332d83"
    assert source_lock["starting_origin_main"] == source_lock["starting_commit"]
    assert source_lock["starting_ahead"] == source_lock["starting_behind"] == 0

    # Family A scope stays bounded and keeps prohibited work out.
    assert prereg["status"] == "PREREGISTERED_NOT_ACTIVATED"
    assert prereg["formal_scope"]["authorized_family"] == "FAMILY_A_ONLY"
    excluded_scope = set(prereg["formal_scope"]["excluded"])
    for item in (
        "Family_B",
        "direct_actuator",
        "W1_real_workload",
        "Aerostack2",
        "R1_delayed_old_session_packet",
        "producer_session_rollover",
        "delayed_old_session_message",
        "HITL",
        "real_flight",
        "unbounded_campaign",
        "stress_only_primary_input",
    ):
        assert item in excluded_scope
    assert "direct_actuator" not in prereg["formal_scope"]["runtime_mechanisms"]

    # Seed integrity, evidence provenance, replay separation, and exclusions.
    required_seed_fields = {
        "seed_id",
        "source_campaign",
        "source_artifact",
        "source_commit",
        "SUT_revision",
        "current_or_historical",
        "runtime_or_replay",
        "mechanism",
        "source_route",
        "target_or_retained_route",
        "lifecycle_sequence",
        "public_trigger",
        "source_evidence_status",
        "setpoint_level",
        "health_behavior",
        "setpoint_behavior",
        "expected_successor",
        "expected_fallback",
        "adapter",
        "realism_level",
        "accepted_source_evidence",
        "route_oracle_applicable",
        "freshness_oracle_applicable",
        "successor_oracle_applicable",
        "applicable_oracles",
        "allowed_variations",
        "prohibited_variations",
        "inclusion_status",
        "exclusion_reason",
        "integrity_status",
    }
    assert required_seed_fields <= set(seeds[0])
    assert len({row["seed_id"] for row in seeds}) == len(seeds) == 61
    runtime = [row for row in seeds if row["inclusion_status"] == "ACCEPTED_RUNTIME_SEED"]
    replay = [row for row in seeds if row["inclusion_status"] == "ACCEPTED_REPLAY_BENCHMARK"]
    excluded = [row for row in seeds if row["inclusion_status"] == "EXCLUDED"]
    assert (len(runtime), len(replay), len(excluded)) == (50, 1, 10)
    allowed_runtime_sources = {"P0", "P0D", "P2", "P3", "P5", "FRESHNESS", "N1", "C1"}
    current_sut = source_lock["dependency_identity"]["PX4"]
    for row in seeds:
        assert row["inclusion_status"] in {
            "ACCEPTED_RUNTIME_SEED",
            "ACCEPTED_REPLAY_BENCHMARK",
            "EXCLUDED",
            "UNRESOLVED",
        }
        assert row["realism_level"] in {"R1", "R2", "R3"}
        assert row["integrity_status"].startswith("PASS")
        assert (ROOT / row["source_artifact"]).exists(), row["seed_id"]
        assert (ROOT / row["accepted_source_evidence"]).exists(), row["seed_id"]
        assert_ancestor(row["source_commit"])
        expected_oracles = "|".join(
            name
            for name, field in (
                ("ROUTE", "route_oracle_applicable"),
                ("FRESHNESS", "freshness_oracle_applicable"),
                ("SUCCESSOR", "successor_oracle_applicable"),
            )
            if row[field] == "true"
        ) or "NONE"
        assert row["applicable_oracles"] == expected_oracles
    for row in runtime:
        assert row["source_campaign"] in allowed_runtime_sources
        assert row["current_or_historical"] == "CURRENT"
        assert row["runtime_or_replay"] == "RUNTIME"
        assert row["SUT_revision"] == current_sut
        assert row["source_evidence_status"]
        assert row["exclusion_reason"] == "NONE"
    assert replay[0]["seed_id"] == "ISSUE162_HISTORICAL_REPLAY"
    assert replay[0]["current_or_historical"] == "HISTORICAL"
    assert replay[0]["runtime_or_replay"] == "REPLAY_ONLY"
    assert "CURRENT_RUNTIME" in replay[0]["prohibited_variations"]
    for source in ("R1", "W1", "B1", "ORACLE_VALIDATION"):
        assert all(row["inclusion_status"] == "EXCLUDED" for row in seeds if row["source_campaign"] == source)
    assert all("direct_actuator" not in row["mechanism"].lower() for row in runtime)
    assert all("family_b" not in row["mechanism"].lower() for row in runtime)
    assert all("SESSION" in row["prohibited_variations"] for row in runtime if row["source_campaign"] == "P0D")

    # State identity and command-age domains are frozen without run identity.
    fields = {item["name"] for item in state["state_fields"]}
    required_state_fields = {
        "declared_mode", "user_intended_mode", "source_route_epoch", "target_route_epoch",
        "active_route_epoch", "registration_state", "registration_instance_id", "activation_id",
        "executor_in_charge", "lifecycle_owner", "producer_identity", "producer_session_id",
        "active_producers", "setpoint_level", "setpoint_publication_state",
        "setpoint_subject_timestamp", "command_age_bucket", "controller_consumption_state",
        "controller_lineage", "allocator_lineage", "actuator_writer_lineage", "health_request_state",
        "health_reply_state", "failsafe_state", "completion_state", "successor_state", "task_phase",
        "vehicle_state_bucket", "evidence_completeness", "clock_bridge_state",
    }
    assert required_state_fields <= fields
    assert len(state["state_fields"]) == 33
    assert set(state["command_age_buckets"]) >= {
        "precedence", "FRESH", "RETAINED_SHORT", "RETAINED_MEDIUM",
        "RETAINED_LONG", "POST_REVOCATION", "UNKNOWN",
    }
    semantic_exclusions = set(state["canonical_state_hash"]["excluded_fields"])
    assert {"run_id", "attempt_id", "wall_clock_timestamp", "raw_artifact_path"} <= semantic_exclusions

    # Reachable event grammar and bounded variation grammar have complete fields.
    edge_required = set(events["edge_required_fields"])
    assert events["edge_count"] == len(events["edges"]) == 26
    assert len({edge["edge_id"] for edge in events["edges"]}) == 26
    for edge in events["edges"]:
        assert edge_required <= set(edge), edge["edge_id"]
        assert edge["source_state_predicate"]
        assert edge["public_trigger"]
        assert edge["provenance"]
    assert events["composition_rules"]["maximum_authority_events_initial_v0"] == 2
    prohibited_events = set(events["composition_rules"]["prohibited"])
    assert {"direct_nav_state_write", "direct_route_epoch_write", "arbitrary_actuator_command"} <= prohibited_events

    operator_required = set(mutations["operator_required_fields"])
    assert operator_required == {
        "operator_id", "applicable_seed_classes", "source_state_predicate", "parameter_domain",
        "parameter_provenance", "realism_level", "expected_state_effect", "safety_constraints",
        "applicable_oracles", "minimization_rule", "prohibited_combinations",
    }
    assert mutations["operator_count"] == len(mutations["operators"]) == 27
    assert len({operator["operator_id"] for operator in mutations["operators"]}) == 27
    for operator in mutations["operators"]:
        assert operator_required <= set(operator), operator["operator_id"]
        assert operator["parameter_provenance"]
    operators_by_id = {operator["operator_id"]: operator for operator in mutations["operators"]}
    assert operators_by_id["TM_UPDATE_INTERVAL"]["parameter_domain"] == {"publication_interval_ms": [50]}
    assert operators_by_id["MC_BOUNDED_TURN"]["parameter_domain"] == {
        "horizontal_speed_m_s": [0.3], "turn_rate_rad_s": [0.15]
    }
    assert operators_by_id["MC_BOUNDED_DESCENT"]["parameter_domain"] == {
        "vertical_speed_m_s_NED": [0.2], "direction": ["DESCENT"]
    }
    globally_prohibited = set(mutations["globally_prohibited_mutations"])
    assert {
        "producer_session_rollover", "delayed_old_session_packet", "Family_B_controller_switch",
        "direct_actuator", "unsupported_replacement_executor_composition", "unbounded_event_sequence",
        "Oracle_threshold_change", "post_execution_mutation_distribution_change",
    } <= globally_prohibited
    assert mutations["conditionally_disabled"]["bounded_DDS_delay_drop_reorder"]["enabled"] is False
    assert mutations["conditionally_disabled"]["acceleration_and_braking_parameterization"]["enabled"] is False

    # Equal budgets and the preregistered selection rules are immutable.
    strategy_rows = strategies["strategies"]
    assert [row["strategy_id"] for row in strategy_rows] == [
        "OFFICIAL_SEQUENCE", "BOUNDED_RANDOM_TIMING_COMPARATOR", "STATE_AWARE_MUTATION"
    ]
    budgets = [row["future_formal_attempt_budget"] for row in strategy_rows]
    assert budgets == [12, 12, 12]
    assert strategies["equal_budget_assertions"]["budget_vector"] == budgets
    assert strategies["equal_budget_assertions"]["total_future_formal_runtime_budget"] == 36
    comparison_phases = [phase for phase in campaign["phases"] if phase["included_in_comparison_budget"]]
    assert [phase["maximum_future_formal_attempts"] for phase in comparison_phases] == budgets
    assert campaign["budget_rules"]["total_future_formal_comparison_attempts"] == 36
    assert campaign["budget_rules"]["current_task_formal_attempts"] == 0
    assert "200" not in (BASE / "campaign_matrix.yaml").read_text(encoding="utf-8")
    assert analysis["state_aware_selection"]["runtime_weight_or_priority_change"] == "forbidden"
    assert analysis["state_aware_selection"]["coverage_map_update"] == "after_ACCEPTED_attempt_only"
    assert analysis["state_aware_selection"]["rejected_attempt_updates_coverage"] is False

    # Oracle, schema, clock, and evidence identities resolve exactly.
    assert oracle_lock["route_oracle"]["version"] == "0.4"
    assert oracle_lock["freshness_oracle"]["version"] == "0.1"
    assert oracle_lock["successor_progression_oracle"]["version"] == "0.1"
    assert oracle_lock["authority_event_linearization_oracle"]["version"] == "0.2"
    assert oracle_lock["identity_consistency"]["old_Route_Oracle_0_3_identity_used"] is False
    assert oracle_lock["identity_consistency"]["unresolved_identity_blockers"] == []
    identity_records = list(iter_identity_records(oracle_lock))
    assert len(identity_records) >= 18
    for record in identity_records:
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert sha256(path) == record["sha256"], record["path"]
    for record in source_lock["protected_authority_artifacts"]:
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert sha256(path) == record["sha256"], record["path"]
    assert oracle_lock["outcome_semantics"]["UNKNOWN_is_PASS"] is False
    assert oracle_lock["outcome_semantics"]["NOT_APPLICABLE_is_PASS"] is False
    assert oracle_lock["outcome_semantics"]["EXPOSURE_is_VIOLATION"] is False
    assert evidence["non_collapsing_semantics"] == {
        "UNKNOWN_to_PASS": "forbidden",
        "NOT_APPLICABLE_to_PASS": "forbidden",
        "EXPOSURE_to_VIOLATION": "forbidden",
        "rejected_attempt_to_SUT_failure": "forbidden",
        "historical_replay_to_current_natural_finding": "forbidden",
        "cleanup_event_to_formal_target_outcome": "forbidden",
    }

    # Safety, evidence, analysis, and zero accounting remain complete and closed.
    required_stops = {
        "PX4_abort", "Gazebo_clock_stall", "non_finite_command",
        "non_finite_controller_observation", "non_finite_actuator_observation",
        "height_boundary_exceeded", "horizontal_speed_boundary_exceeded",
        "vertical_speed_boundary_exceeded", "attitude_boundary_exceeded",
        "body_rate_boundary_exceeded", "unexpected_ground_contact", "runner_timeout",
    }
    assert required_stops <= set(safety["immediate_stop_conditions"])
    assert safety["physical_boundaries"]["W1_or_B1_envelope_used"] is False
    assert safety["current_task_assertions"] == {
        "PX4_started": False,
        "Gazebo_started": False,
        "ROS_started": False,
        "DDS_started": False,
        "runtime_attempts": 0,
    }
    coverage_metrics = set(analysis["coverage_metrics"])
    assert len(coverage_metrics) == 10
    assert "unique_admissible_FuzzState_count" in coverage_metrics
    assert analysis["comparison_rules"]["equal_formal_attempt_budget"] == "12_per_arm"
    assert analysis["claim_limits"] == [
        "no_PX4_population_defect_rate",
        "no_general_state_aware_superiority",
        "no_full_method_effectiveness",
        "no_real_world_deployment_validity",
        "no_Family_B_runtime_generality",
    ]

    assert ledger["activation_commit"] is None
    assert ledger["status"] == "NOT_STARTED"
    assert ledger["formal_attempts"] == ledger["qualification_attempts"] == 0
    assert ledger["strategy_counts"] == {
        "OFFICIAL_SEQUENCE": 0,
        "BOUNDED_RANDOM_TIMING_COMPARATOR": 0,
        "STATE_AWARE_MUTATION": 0,
    }
    assert ledger["next_attempt_id"] is None
    assert ledger["attempts"] == []
    assert prereg["current_state"]["formal_attempts"] == 0
    assert prereg["current_state"]["state_aware_search_gain_supported"] is False
    assert prereg["current_state"]["full_method_effectiveness_supported"] is False

    schema = read_json(ACTIVATION_SCHEMA)
    jsonschema.Draft202012Validator(schema).validate(activation)
    assert activation["campaign_activated"] is False
    assert activation["runtime_authorized"] is False
    assert activation["formal_attempts_authorized"] is False
    assert activation["authorized_family"] == "FAMILY_A_ONLY"
    assert activation["activation_requires_separate_commit"] is True
    assert activation["activation_requires_explicit_review"] is True
    for completed_field in (
        "preregistration_complete", "source_lock_complete", "seed_catalog_complete",
        "state_model_complete", "event_grammar_complete", "mutation_grammar_complete",
        "strategy_matrix_complete", "budgets_frozen", "oracle_identity_complete",
        "evidence_rules_complete", "safety_rules_complete", "analysis_plan_complete",
        "consistency_check_passed", "focused_tests_passed", "validate_repo_passed",
    ):
        assert activation[completed_field] is True

    next_action = "review the frozen Family A Fuzzer v0 preregistration and create a separate activation decision"
    assert prereg["current_state"]["next_exact_action"] == next_action
    assert activation["next_exact_action"] == next_action

    current_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "docs/narrative/CURRENT_NARRATIVE.md",
            "docs/repository/CURRENT_GOAL_STATE.md",
            "docs/repository/MOTIVATION_COMPLETION_STATE.md",
        )
    )
    assert "PREREGISTERED_NOT_ACTIVATED" in current_text
    assert "formal attempts: `0`" in current_text
    assert "state-aware search gain: `not_established`" in current_text.lower()
    assert "full method effectiveness: `not_established`" in current_text.lower()
    review_decision_path = BASE / "activation_review/qualification_activation_decision.json"
    if review_decision_path.is_file():
        review_decision = read_json(review_decision_path)
        assert review_decision["decision"] == "DECLINE_IMPLEMENTATION_NOT_READY"
        assert review_decision["status"] == "QUALIFICATION_NOT_AUTHORIZED"
        assert review_decision["qualification_authorized"] is False
        assert review_decision["runtime_authorized"] is False
        assert review_decision["current_formal_attempts"] == 0
        readiness_gate = BASE / "readiness_amendment/static_readiness_gate.json"
        if readiness_gate.is_file():
            rereview_decision = (
                BASE
                / "activation_rereview/qualification_activation_decision.json"
            )
            if rereview_decision.is_file():
                assert (
                    "create an independent blocker-resolution amendment for "
                    "the new review findings"
                    in current_text
                )
            else:
                assert (
                    "perform a new independent static qualification activation review"
                    in current_text
                )
        else:
            assert review_decision["next_exact_action"] in current_text
    else:
        assert next_action in current_text
    for false_claim in (
        "campaign is activated",
        "state-aware search gain is established",
        "full method effectiveness is established",
    ):
        assert false_claim not in current_text.lower()

    tracked_runs = subprocess.run(
        ["git", "ls-files", "runs"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked_runs == []
    family_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in BASE.iterdir()
        if path.is_file()
    )
    private_prefixes = ("/" + "home/", "/" + "mnt/")
    assert all(prefix not in family_text for prefix in private_prefixes)

    return {
        "seed_records": len(seeds),
        "runtime_seeds": len(runtime),
        "historical_replay_seeds": len(replay),
        "excluded_seeds": len(excluded),
        "state_fields": len(state["state_fields"]),
        "event_edges": len(events["edges"]),
        "variation_operators": len(mutations["operators"]),
        "comparison_budget": sum(budgets),
        "formal_attempts": ledger["formal_attempts"],
        "tracked_raw_files": len(tracked_runs),
        "oracle_identity_records": len(identity_records),
    }


def main() -> None:
    result = validate()
    print("Family A Fuzzer v0 preregistration consistency check passed")
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
