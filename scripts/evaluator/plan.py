#!/usr/bin/env python3
"""Strict validation for a newly preregistered Family A experiment plan."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.model.runtime_route import EVENT_KINDS, ROUTES


STRATEGIES = {"official_sequence", "bounded_random_timing", "state_aware"}
THRESHOLDS = {
    "revocation_deadline_ns",
    "installation_deadline_ns",
    "maximum_effect_gap_ns",
    "maximum_command_age_ns",
    "successor_deadline_ns",
    "fallback_deadline_ns",
}
SAFE_ROUTES = {
    "internal_hold",
    "internal_rtl",
    "internal_land",
    "internal_recovery",
}
TARGET_KINDS = {"sitl", "hitl", "flight_hardware"}
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class PlanError(ValueError):
    """Experiment plan is incomplete or outside Family A."""


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanError(f"{name} must be an object")
    return value


def validate_plan(plan: dict[str, Any], *, allow_template: bool = False) -> None:
    required = {
        "schema_version",
        "plan_id",
        "run_id",
        "strategy",
        "transition",
        "thresholds",
        "required_event_kinds",
        "source_identity",
        "execution_environment",
        "cleanup",
    }
    version = plan.get("schema_version")
    if version == "1.3":
        required.add("workload")
    if set(plan) != required:
        raise PlanError("plan fields differ from the current schema")
    if version not in {"1.2", "1.3"}:
        raise PlanError("plan schema_version must be 1.2 or 1.3")
    for field in ("plan_id", "run_id"):
        value = plan[field]
        if not isinstance(value, str) or not value.strip():
            raise PlanError(f"{field} must be a non-empty string")
        if not allow_template and value.startswith("REPLACE-"):
            raise PlanError(f"{field} still contains a template placeholder")

    strategy = _mapping(plan["strategy"], "strategy")
    if set(strategy) != {"name", "seed", "simulation_seed", "timing_bounds_ns"}:
        raise PlanError("strategy fields differ from the current schema")
    if strategy["name"] not in STRATEGIES:
        raise PlanError("unsupported strategy")
    if strategy["name"] == "official_sequence" and strategy["seed"] is not None:
        raise PlanError("official_sequence must not declare a random seed")
    if strategy["name"] != "official_sequence" and not isinstance(strategy["seed"], int):
        raise PlanError("timing and state-aware strategies require an integer seed")
    if not isinstance(strategy["simulation_seed"], int) or strategy["simulation_seed"] <= 0:
        raise PlanError("simulation_seed must be a positive integer")
    bounds = _mapping(strategy["timing_bounds_ns"], "timing_bounds_ns")
    for name, interval in bounds.items():
        if (
            not isinstance(name, str)
            or not isinstance(interval, list)
            or len(interval) != 2
            or not all(isinstance(value, int) and value >= 0 for value in interval)
            or interval[0] > interval[1]
        ):
            raise PlanError("each timing bound must be an ordered non-negative pair")

    transition = _mapping(plan["transition"], "transition")
    transition_fields = {
        "source_route",
        "target_route",
        "expected_successor",
        "expected_fallback",
        "expected_lifecycle_owner",
        "expected_executor_owner",
        "target_activation_expected",
        "target_activation_count",
        "registration_rejection_expected",
        "activation_rejection_expected",
        "completion_expected",
        "fault_expected",
        "fallback_expected",
    }
    if set(transition) != transition_fields:
        raise PlanError("transition fields differ from the current schema")
    for field in ("source_route", "target_route", "expected_successor", "expected_fallback"):
        if transition[field] not in ROUTES:
            raise PlanError(f"unsupported {field}")
    if transition["source_route"] == transition["target_route"]:
        raise PlanError("a route-replacing transition must change routes")
    if transition["expected_fallback"] not in SAFE_ROUTES:
        raise PlanError("expected_fallback must be an internal safe route")
    for field in ("expected_lifecycle_owner", "expected_executor_owner"):
        if not isinstance(transition[field], str) or not transition[field].strip():
            raise PlanError(f"{field} must be a non-empty string")
    for field in (
        "target_activation_expected",
        "registration_rejection_expected",
        "activation_rejection_expected",
        "completion_expected",
        "fault_expected",
        "fallback_expected",
    ):
        if not isinstance(transition[field], bool):
            raise PlanError(f"{field} must be boolean")
    activation_count = transition["target_activation_count"]
    if (
        not isinstance(activation_count, list)
        or len(activation_count) != 2
        or not all(isinstance(value, int) and value >= 0 for value in activation_count)
        or activation_count[0] > activation_count[1]
    ):
        raise PlanError("target_activation_count must be an ordered non-negative pair")
    if transition["target_activation_expected"] and activation_count[0] < 1:
        raise PlanError("an expected target activation requires a positive count")
    if not transition["target_activation_expected"] and activation_count != [0, 0]:
        raise PlanError("a rejected activation must have target_activation_count [0, 0]")
    if transition["completion_expected"] and not transition["target_activation_expected"]:
        raise PlanError("completion requires target activation")
    if transition["activation_rejection_expected"]:
        if transition["target_activation_expected"]:
            raise PlanError("target activation and activation rejection are mutually exclusive")
        if not transition["fault_expected"]:
            raise PlanError("activation rejection requires an expected fault observation")
    if not transition["target_activation_expected"] and not transition[
        "activation_rejection_expected"
    ]:
        raise PlanError("a plan must expect target activation or its explicit rejection")
    if transition["fallback_expected"] and not transition["fault_expected"]:
        raise PlanError("fallback installation requires an expected fault")

    thresholds = _mapping(plan["thresholds"], "thresholds")
    if set(thresholds) != THRESHOLDS or any(
        not isinstance(value, int) or value <= 0 for value in thresholds.values()
    ):
        raise PlanError("thresholds must contain the six positive integer bounds")

    kinds = plan["required_event_kinds"]
    if (
        not isinstance(kinds, list)
        or len(kinds) != len(set(kinds))
        or any(kind not in EVENT_KINDS for kind in kinds)
    ):
        raise PlanError("required_event_kinds must be unique supported event names")
    mandatory = {
        "collection_started",
        "collection_stopped",
        "environment_attested",
    }
    if transition["target_activation_expected"]:
        mandatory.update(
            {
                "transition_requested",
                "revocation",
                "activation",
                "command_consumed",
                "controller_output",
                "allocator_output",
                "actuator_write",
            }
        )
    if transition["activation_rejection_expected"]:
        mandatory.add("activation_requested")
    if transition["registration_rejection_expected"]:
        mandatory.add("registration")
    if transition["completion_expected"]:
        mandatory.add("completion")
    if transition["fault_expected"]:
        mandatory.add("fault_detected")
    if transition["fallback_expected"]:
        mandatory.add("fallback_triggered")
    if "adjacent_after_activation_ns" in bounds:
        mandatory.add("adjacent_request")
    if not mandatory <= set(kinds):
        raise PlanError("required_event_kinds omits a mandatory route contract event")

    if version == "1.3":
        workload = _mapping(plan["workload"], "workload")
        fields = {
            "profile_id", "profile_digest", "setpoint_semantics", "phases",
            "injection_phase", "physical_analysis_plan_digest", "observer_profile",
            "observer_config_digest", "physical_validity",
        }
        if set(workload) != fields:
            raise PlanError("workload fields differ from schema 1.3")
        if workload["setpoint_semantics"] not in {"position_only", "position_plus_velocity"}:
            raise PlanError("unsupported setpoint semantics")
        phases = workload["phases"]
        if not isinstance(phases, list) or not phases or len(phases) != len(set(phases)):
            raise PlanError("workload phases must be a non-empty unique list")
        if workload["injection_phase"] not in phases:
            raise PlanError("injection phase must name a frozen workload phase")
        if workload["observer_profile"] not in {"baseline", "transition"}:
            raise PlanError("unsupported formal observer profile")
        for field in ("profile_digest", "physical_analysis_plan_digest", "observer_config_digest"):
            if DIGEST.fullmatch(str(workload[field])) is None:
                raise PlanError(f"workload.{field} must be an exact SHA-256 digest")
        physical = _mapping(workload["physical_validity"], "physical_validity")
        physical_fields = {
            "minimum_takeoff_height_m", "takeoff_dwell_s",
            "minimum_motion_entry_progress_m", "minimum_nominal_completion_progress_m",
        }
        if set(physical) != physical_fields or any(
            not isinstance(value, (int, float)) or value < 0 for value in physical.values()
        ) or physical["minimum_takeoff_height_m"] <= 0 or physical["minimum_motion_entry_progress_m"] <= 0 or physical["minimum_nominal_completion_progress_m"] <= 0:
            raise PlanError("physical validity contract is incomplete")

    identity = _mapping(plan["source_identity"], "source_identity")
    if set(identity) != {"repository_commit", "dependency_lock_digest"}:
        raise PlanError("source_identity fields differ from the current schema")
    if (
        not allow_template
        and COMMIT.fullmatch(str(identity["repository_commit"])) is None
    ):
        raise PlanError("repository_commit must be an exact 40-character commit")
    if (
        not allow_template
        and DIGEST.fullmatch(str(identity["dependency_lock_digest"])) is None
    ):
        raise PlanError("dependency_lock_digest must be an exact SHA-256 digest")

    environment = _mapping(plan["execution_environment"], "execution_environment")
    environment_fields = {
        "environment_id",
        "execution_host_id",
        "collector_host_id",
        "target_kind",
        "architecture",
        "operating_system",
        "px4_binary_digest",
        "environment_manifest_digest",
    }
    if set(environment) != environment_fields:
        raise PlanError("execution_environment fields differ from the current schema")
    for field in environment_fields - {
        "px4_binary_digest",
        "environment_manifest_digest",
    }:
        value = environment[field]
        if not isinstance(value, str) or not value.strip():
            raise PlanError(f"execution_environment.{field} must be a non-empty string")
        if not allow_template and value.startswith("REPLACE-"):
            raise PlanError(
                f"execution_environment.{field} still contains a template placeholder"
            )
    if not allow_template and environment["target_kind"] not in TARGET_KINDS:
        raise PlanError("execution_environment.target_kind is unsupported")
    for field in ("px4_binary_digest", "environment_manifest_digest"):
        if not allow_template and DIGEST.fullmatch(str(environment[field])) is None:
            raise PlanError(f"execution_environment.{field} must be an exact SHA-256 digest")

    cleanup = _mapping(plan["cleanup"], "cleanup")
    if set(cleanup) != {"require_landed", "require_disarmed", "safe_terminal_routes"}:
        raise PlanError("cleanup fields differ from the current schema")
    if not isinstance(cleanup["require_landed"], bool) or not isinstance(
        cleanup["require_disarmed"], bool
    ):
        raise PlanError("cleanup terminal requirements must be boolean")
    safe = cleanup["safe_terminal_routes"]
    if not isinstance(safe, list) or not safe or not set(safe) <= SAFE_ROUTES:
        raise PlanError("cleanup safe_terminal_routes are invalid")


def load_plan(path: Path, *, allow_template: bool = False) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PlanError("plan root must be an object")
    validate_plan(value, allow_template=allow_template)
    return value
