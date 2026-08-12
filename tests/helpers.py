from __future__ import annotations

from copy import deepcopy
from typing import Any

from scripts.model.runtime_route import ZERO_HASH, event_digest


def identity(route: str, label: str) -> dict[str, str]:
    return {
        "route": route,
        "route_epoch": f"epoch-{label}",
        "producer_session": f"session-{label}",
        "registration_id": f"registration-{label}",
        "activation_id": f"activation-{label}",
        "controller_id": f"controller-{label}",
        "allocator_id": f"allocator-{label}",
        "writer_id": f"writer-{label}",
        "lifecycle_owner": f"lifecycle-{label}",
        "executor_owner": f"executor-{label}",
    }


def plan() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "plan_id": "plan-family-a-001",
        "run_id": "run-family-a-001",
        "strategy": {
            "name": "official_sequence",
            "seed": None,
            "timing_bounds_ns": {},
        },
        "transition": {
            "source_route": "legacy_offboard",
            "target_route": "dynamic_external_mode",
            "expected_successor": "internal_hold",
            "expected_fallback": "internal_land",
            "expected_lifecycle_owner": "lifecycle-target",
            "expected_executor_owner": "executor-target",
            "completion_expected": True,
            "fault_expected": False,
        },
        "thresholds": {
            "revocation_deadline_ns": 300_000_000,
            "installation_deadline_ns": 300_000_000,
            "maximum_effect_gap_ns": 20_000_000,
            "maximum_command_age_ns": 100_000_000,
            "successor_deadline_ns": 300_000_000,
            "fallback_deadline_ns": 300_000_000,
        },
        "required_event_kinds": [
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
        ],
        "source_identity": {
            "repository_commit": "1" * 40,
            "dependency_lock_digest": "sha256:" + "2" * 64,
        },
        "execution_environment": {
            "environment_id": "target-lab-a",
            "execution_host_id": "runner-a",
            "collector_host_id": "collector-a",
            "target_kind": "sitl",
            "architecture": "linux/arm64",
            "operating_system": "ubuntu-24.04",
            "px4_binary_digest": "sha256:" + "3" * 64,
            "environment_manifest_digest": "sha256:" + "4" * 64,
        },
        "cleanup": {
            "require_landed": True,
            "require_disarmed": True,
            "safe_terminal_routes": ["internal_hold", "internal_land"],
        },
    }


def raw_event(kind: str, timestamp_ns: int, **values: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": "run-family-a-001",
        "sequence": 0,
        "kind": kind,
        "timestamp_ns": timestamp_ns,
        "source_domain": "px4_boot",
        **values,
    }


def passing_raw_events() -> list[dict[str, Any]]:
    source = identity("legacy_offboard", "source")
    target = identity("dynamic_external_mode", "target")
    successor = identity("internal_hold", "successor")
    return [
        raw_event("collection_started", 0),
        raw_event(
            "environment_attested",
            1_000_000,
            execution_environment=plan()["execution_environment"],
        ),
        raw_event("activation", 10_000_000, **source),
        raw_event("actuator_write", 115_000_000, command_subject_ns=100_000_000, **source),
        raw_event(
            "transition_requested",
            110_000_000,
            source_route="legacy_offboard",
            target_route="dynamic_external_mode",
        ),
        raw_event("revocation", 116_000_000, **source),
        raw_event("activation", 120_000_000, **target),
        raw_event("command_consumed", 122_000_000, command_subject_ns=115_000_000, **target),
        raw_event("controller_output", 124_000_000, command_subject_ns=115_000_000, **target),
        raw_event("allocator_output", 126_000_000, command_subject_ns=115_000_000, **target),
        raw_event("actuator_write", 128_000_000, command_subject_ns=115_000_000, **target),
        raw_event("completion", 150_000_000, route="dynamic_external_mode"),
        raw_event("revocation", 151_000_000, **target),
        raw_event("activation", 160_000_000, **successor),
        raw_event("command_consumed", 162_000_000, command_subject_ns=155_000_000, **successor),
        raw_event("controller_output", 164_000_000, command_subject_ns=155_000_000, **successor),
        raw_event("allocator_output", 166_000_000, command_subject_ns=155_000_000, **successor),
        raw_event("actuator_write", 168_000_000, command_subject_ns=155_000_000, **successor),
        raw_event(
            "terminal_state",
            170_000_000,
            route="internal_hold",
            landed=True,
            disarmed=True,
        ),
        raw_event("collection_stopped", 500_000_000),
    ]


def chain(raw_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = ZERO_HASH
    chained = []
    for sequence, raw in enumerate(deepcopy(raw_events)):
        raw["sequence"] = sequence
        raw["previous_hash"] = previous
        raw.pop("event_hash", None)
        raw["event_hash"] = event_digest(raw)
        previous = raw["event_hash"]
        chained.append(raw)
    return chained


def passing_events() -> list[dict[str, Any]]:
    return chain(passing_raw_events())
