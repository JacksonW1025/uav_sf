#!/usr/bin/env python3
"""Freeze and validate one executable decision for a registered live action."""

from __future__ import annotations

from dataclasses import dataclass
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


STATE = {"route_active": True, "motion_entered": True}
OFFSETS_NS = (
    ("early", 3_500_000_000),
    ("pre_boundary", 4_250_000_000),
    ("boundary", 5_000_000_000),
    ("post_boundary", 5_750_000_000),
    ("late", 6_500_000_000),
)
SUPPORTED_STRATEGIES = {
    "official_sequence",
    "bounded_random_timing",
    "state_aware",
}


@dataclass(frozen=True)
class LiveActionContract:
    backend: str
    action: str
    boundary_prefix: str


CONTRACTS = {
    contract.backend: contract
    for contract in (
        LiveActionContract(
            backend="owned_setpoint_stall_v1",
            action="setpoint_stall",
            boundary_prefix="stall_offset",
        ),
        LiveActionContract(
            backend="owned_process_exit_fallback_v1",
            action="process_exit",
            boundary_prefix="exit_offset",
        ),
    )
}


def live_action_contract(backend: str) -> LiveActionContract:
    try:
        return CONTRACTS[backend]
    except KeyError as exc:
        raise LiveStrategyError(f"unsupported live strategy backend: {backend}") from exc


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
    backend: str = "owned_setpoint_stall_v1",
) -> dict[str, Any]:
    contract = live_action_contract(backend)
    action = contract.action
    bounds = timing_bounds_ns.get(action)
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise LiveStrategyError(f"{action} timing bounds are required")
    lower, upper = bounds
    if not all(isinstance(value, int) for value in bounds) or lower < 0 or upper < lower:
        raise LiveStrategyError(f"{action} timing bounds are invalid")
    if not isinstance(official_offset_ns, int):
        raise LiveStrategyError("official action offset must be an integer")
    if not all(isinstance(value, str) for value in covered_boundaries):
        raise LiveStrategyError("covered boundaries must be strings")
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
        official_sequence([action])
        selected_offset = official_offset_ns
    elif strategy == "bounded_random_timing":
        if seed is None:
            raise LiveStrategyError("bounded random timing requires a seed")
        selected_offset = int(
            bounded_random_timing([action], {action: bounds}, seed=seed)[0]["delay_ns"]
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
                    covers=(f"{contract.boundary_prefix}:{name}",),
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
        "backend": contract.backend,
        "strategy": strategy,
        "seed": seed,
        "action": action,
        "required_state": STATE,
        "timing_bounds_ns": bounds,
        "official_offset_ns": official_offset_ns,
        "planned_offset_ns": selected_offset,
        "selected_boundary": f"{contract.boundary_prefix}:{boundary}",
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
    contract = live_action_contract(str(value.get("backend", "")))
    if value.get("action") != contract.action:
        raise LiveStrategyError("live strategy decision action differs from its backend")
    covered = value.get("covered_boundaries_before_decision")
    if not isinstance(covered, list) or not all(isinstance(item, str) for item in covered):
        raise LiveStrategyError("live strategy coverage feedback is invalid")
    bounds = value.get("timing_bounds_ns")
    strategy = value.get("strategy")
    if strategy not in SUPPORTED_STRATEGIES:
        raise LiveStrategyError("live strategy decision names an unsupported strategy")
    expected = create_live_decision(
        strategy=strategy,
        seed=value.get("seed"),
        timing_bounds_ns={contract.action: bounds},
        official_offset_ns=value.get("official_offset_ns"),
        covered_boundaries=set(covered),
        backend=contract.backend,
    )
    if value != expected:
        raise LiveStrategyError("live strategy decision differs from the registered contract")
