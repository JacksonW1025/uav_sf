#!/usr/bin/env python3
"""Normalize Family A source observations into canonical route events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from scripts.model.runtime_route import EVENT_KINDS, ROUTES, RouteModelError, validate_event


MECHANISM_ROUTE = {
    "px4_internal": "px4_internal",
    "legacy_offboard": "legacy_offboard",
    "dynamic_external_mode": "dynamic_external_mode",
    "mode_executor": "mode_executor",
    "internal_hold": "internal_hold",
    "internal_rtl": "internal_rtl",
    "internal_land": "internal_land",
    "internal_recovery": "internal_recovery",
}

FIELD_ALIASES = {
    "event": "kind",
    "analysis_timestamp_ns": "timestamp_ns",
    "clock_domain": "source_domain",
    "epoch": "route_epoch",
    "session_id": "producer_session",
    "registration": "registration_id",
    "activation": "activation_id",
    "command_timestamp_ns": "command_subject_ns",
    "controller": "controller_id",
    "allocator": "allocator_id",
    "writer": "writer_id",
}


@dataclass(frozen=True)
class FamilyAAdapter:
    mechanism: str

    def __post_init__(self) -> None:
        if self.mechanism not in MECHANISM_ROUTE:
            raise RouteModelError(f"unsupported Family A mechanism: {self.mechanism}")

    def adapt(self, raw: Mapping[str, Any], *, run_id: str) -> dict[str, Any]:
        value = dict(raw)
        for source, target in FIELD_ALIASES.items():
            if source in value and target not in value:
                value[target] = value.pop(source)
        value.setdefault("schema_version", "1.0")
        value["run_id"] = run_id
        value.setdefault("route", MECHANISM_ROUTE[self.mechanism])
        value.setdefault("source_domain", "px4_boot")
        value.setdefault("sequence", 0)
        kind = value.get("kind")
        if kind not in EVENT_KINDS:
            raise RouteModelError(f"unsupported event kind: {kind}")
        if value.get("route") not in ROUTES:
            raise RouteModelError(f"unsupported route: {value.get('route')}")
        validate_event(value, require_chain=False)
        return value


def adapt_event(raw: Mapping[str, Any], *, mechanism: str, run_id: str) -> dict[str, Any]:
    return FamilyAAdapter(mechanism).adapt(raw, run_id=run_id)
