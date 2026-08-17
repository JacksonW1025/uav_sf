#!/usr/bin/env python3
"""Freeze one executable setpoint-stall decision for the shared live backend."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from scripts.evaluator.strategies import (
    ActionCandidate,
    bounded_random_timing,
    choose_state_aware,
    official_sequence,
)


class LiveStrategyError(ValueError):
    """A live strategy decision is outside the registered action contract."""


ACTION = "setpoint_stall"
STATE = {"route_active": True, "motion_entered": True}
OFFSETS_NS = (
    ("early", 3_500_000_000),
    ("pre_boundary", 4_250_000_000),
    ("boundary", 5_000_000_000),
    ("post_boundary", 5_750_000_000),
    ("late", 6_500_000_000),
)


def boundary_for_offset(offset_ns: int) -> str:
    return min(OFFSETS_NS, key=lambda item: (abs(item[1] - offset_ns), item[1]))[0]


def decision_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def create_live_decision(
    *,
    strategy: str,
    seed: int | None,
    timing_bounds_ns: dict[str, list[int]],
    official_offset_ns: int,
    covered_boundaries: set[str],
) -> dict[str, Any]:
    bounds = timing_bounds_ns.get(ACTION)
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise LiveStrategyError("setpoint_stall timing bounds are required")
    lower, upper = bounds
    if not all(isinstance(value, int) for value in bounds) or lower < 0 or upper < lower:
        raise LiveStrategyError("setpoint_stall timing bounds are invalid")
    candidates = [
        {
            "boundary": name,
            "offset_ns": offset,
            "enabled": lower <= offset <= upper,
            "required_state": STATE,
        }
        for name, offset in OFFSETS_NS
    ]
    if strategy == "official_sequence":
        if seed is not None:
            raise LiveStrategyError("official sequence must not use a strategy seed")
        official_sequence([ACTION])
        selected_offset = official_offset_ns
    elif strategy == "bounded_random_timing":
        if seed is None:
            raise LiveStrategyError("bounded random timing requires a seed")
        selected_offset = int(
            bounded_random_timing([ACTION], {ACTION: bounds}, seed=seed)[0]["delay_ns"]
        )
    elif strategy == "state_aware":
        if seed is None:
            raise LiveStrategyError("state-aware selection requires a seed")
        enabled = [item for item in OFFSETS_NS if lower <= item[1] <= upper]
        if not enabled:
            raise LiveStrategyError("no state-aware timing candidate is within bounds")
        candidate = choose_state_aware(
            [
                ActionCandidate(
                    name=name,
                    required_state=tuple(sorted(STATE.items())),
                    covers=(f"stall_offset:{name}",),
                    deadline_distance_ns=offset - official_offset_ns,
                )
                for name, offset in enabled
            ],
            state=STATE,
            covered_contract_boundaries=covered_boundaries,
            seed=seed,
        )
        selected_offset = dict(enabled)[candidate.name]
    else:
        raise LiveStrategyError(f"unsupported live strategy: {strategy}")
    if not lower <= selected_offset <= upper:
        raise LiveStrategyError("selected action offset is outside its frozen bounds")
    boundary = boundary_for_offset(selected_offset)
    return {
        "schema_version": "1.0",
        "backend": "owned_setpoint_stall_v1",
        "strategy": strategy,
        "seed": seed,
        "action": ACTION,
        "required_state": STATE,
        "timing_bounds_ns": bounds,
        "official_offset_ns": official_offset_ns,
        "planned_offset_ns": selected_offset,
        "selected_boundary": f"stall_offset:{boundary}",
        "covered_boundaries_before_decision": sorted(covered_boundaries),
        "candidates": candidates,
    }


def validate_live_decision(value: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "backend",
        "strategy",
        "seed",
        "action",
        "required_state",
        "timing_bounds_ns",
        "official_offset_ns",
        "planned_offset_ns",
        "selected_boundary",
        "covered_boundaries_before_decision",
        "candidates",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise LiveStrategyError("live strategy decision shape differs")
    if value.get("backend") != "owned_setpoint_stall_v1" or value.get("action") != ACTION:
        raise LiveStrategyError("live strategy decision backend differs")
    if value.get("required_state") != STATE:
        raise LiveStrategyError("live action precondition differs")
    bounds = value.get("timing_bounds_ns")
    offset = value.get("planned_offset_ns")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or not all(isinstance(item, int) for item in bounds)
        or not isinstance(offset, int)
        or not bounds[0] <= offset <= bounds[1]
    ):
        raise LiveStrategyError("live strategy schedule is invalid")
