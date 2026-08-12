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
    if set(plan) != required:
        raise PlanError("plan fields differ from the current schema")
    if plan["schema_version"] != "1.0":
        raise PlanError("plan schema_version must be 1.0")
    for field in ("plan_id", "run_id"):
        value = plan[field]
        if not isinstance(value, str) or not value.strip():
            raise PlanError(f"{field} must be a non-empty string")
        if not allow_template and value.startswith("REPLACE-"):
            raise PlanError(f"{field} still contains a template placeholder")

    strategy = _mapping(plan["strategy"], "strategy")
    if set(strategy) != {"name", "seed", "timing_bounds_ns"}:
        raise PlanError("strategy fields differ from the current schema")
    if strategy["name"] not in STRATEGIES:
        raise PlanError("unsupported strategy")
    if strategy["name"] == "official_sequence" and strategy["seed"] is not None:
        raise PlanError("official_sequence must not declare a random seed")
    if strategy["name"] != "official_sequence" and not isinstance(strategy["seed"], int):
        raise PlanError("timing and state-aware strategies require an integer seed")
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
        "completion_expected",
        "fault_expected",
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
    for field in ("completion_expected", "fault_expected"):
        if not isinstance(transition[field], bool):
            raise PlanError(f"{field} must be boolean")

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
        "transition_requested",
        "revocation",
        "activation",
        "command_consumed",
        "controller_output",
        "allocator_output",
        "actuator_write",
    }
    if not mandatory <= set(kinds):
        raise PlanError("required_event_kinds omits a mandatory route contract event")

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
