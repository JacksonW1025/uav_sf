#!/usr/bin/env python3
"""Partial V8 Runtime Route Instance and normalized-event skeleton."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


ROUTES = frozenset(
    {
        "px4_internal",
        "legacy_offboard",
        "dynamic_external_mode",
        "mode_executor",
        "internal_hold",
        "internal_rtl",
        "internal_land",
        "internal_recovery",
    }
)

EVENT_KINDS = frozenset(
    {
        "collection_started",
        "collection_stopped",
        "environment_attested",
        "clock_bridge",
        "collector_gap",
        "transition_requested",
        "activation_requested",
        "adjacent_request",
        "registration",
        "activation",
        "revocation",
        "command_published",
        "command_consumed",
        "controller_output",
        "allocator_output",
        "actuator_write",
        "owner_changed",
        "completion",
        "fault_detected",
        "fallback_triggered",
        "terminal_state",
        "cleanup_completed",
    }
)

EFFECT_EVENT_KINDS = frozenset(
    {"command_consumed", "controller_output", "allocator_output", "actuator_write"}
)
# Retained prototype coverage only. Step 1 must replace this with the reviewed
# V8 authority-bearing event set before any combined Gate can exist.
AUTHORITY_EVENT_KINDS = frozenset({"activation", *EFFECT_EVENT_KINDS})
IDENTITY_FIELDS = (
    "route",
    "route_epoch",
    "producer_session",
    "registration_id",
    "activation_id",
    "controller_id",
    "allocator_id",
    "writer_id",
    "lifecycle_owner",
    "executor_owner",
)
ZERO_HASH = "0" * 64


class RouteModelError(ValueError):
    """A route event is not representable by the current model."""


@dataclass(frozen=True)
class RuntimeRouteInstance:
    route: str
    route_epoch: str
    producer_session: str
    registration_id: str
    activation_id: str
    controller_id: str
    allocator_id: str
    writer_id: str
    lifecycle_owner: str
    executor_owner: str

    def __post_init__(self) -> None:
        if self.route not in ROUTES:
            raise RouteModelError(f"unsupported route: {self.route}")
        for name, value in asdict(self).items():
            if name != "route" and (not isinstance(value, str) or not value.strip()):
                raise RouteModelError(f"{name} must be a non-empty string")

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "RuntimeRouteInstance":
        missing = [name for name in IDENTITY_FIELDS if not event.get(name)]
        if missing:
            raise RouteModelError(
                "runtime route identity is incomplete: " + ", ".join(missing)
            )
        return cls(**{name: str(event[name]) for name in IDENTITY_FIELDS})

    def matches(self, event: dict[str, Any]) -> bool:
        return all(event.get(name) == value for name, value in asdict(self).items())


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def event_digest(event_without_digest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(event_without_digest)).hexdigest()


def validate_event(event: dict[str, Any], *, require_chain: bool = True) -> None:
    required = {
        "schema_version",
        "run_id",
        "sequence",
        "kind",
        "timestamp_ns",
        "source_domain",
    }
    if require_chain:
        required.update({"previous_hash", "event_hash"})
    missing = sorted(required - set(event))
    if missing:
        raise RouteModelError("missing event fields: " + ", ".join(missing))
    if event["schema_version"] != "1.0":
        raise RouteModelError("event schema_version must be 1.0")
    if not isinstance(event["run_id"], str) or not event["run_id"].strip():
        raise RouteModelError("run_id must be a non-empty string")
    if not isinstance(event["sequence"], int) or event["sequence"] < 0:
        raise RouteModelError("sequence must be a non-negative integer")
    if event["kind"] not in EVENT_KINDS:
        raise RouteModelError(f"unsupported event kind: {event['kind']}")
    if event["kind"] == "environment_attested" and not isinstance(
        event.get("execution_environment"), dict
    ):
        raise RouteModelError(
            "environment_attested requires an execution_environment object"
        )
    if not isinstance(event["timestamp_ns"], int) or event["timestamp_ns"] < 0:
        raise RouteModelError("timestamp_ns must be a non-negative integer")
    if not isinstance(event["source_domain"], str) or not event["source_domain"]:
        raise RouteModelError("source_domain must be a non-empty string")
    if "route" in event and event["route"] not in ROUTES:
        raise RouteModelError(f"unsupported route: {event['route']}")
    if event["kind"] in EFFECT_EVENT_KINDS:
        subject = event.get("command_subject_ns")
        if not isinstance(subject, int) or subject < 0:
            raise RouteModelError(
                f"{event['kind']} requires a non-negative command_subject_ns"
            )
    if require_chain:
        for field in ("previous_hash", "event_hash"):
            value = event[field]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise RouteModelError(f"{field} must be a lowercase SHA-256 digest")


def read_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RouteModelError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(event, dict):
            raise RouteModelError(f"{path}:{line_number}: event must be an object")
        validate_event(event)
        events.append(event)
    return events


def event_kinds(events: Iterable[dict[str, Any]]) -> set[str]:
    return {str(event["kind"]) for event in events}
