#!/usr/bin/env python3
"""Freeze and validate one executable decision for a registered live action."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from scripts.corpus.core_actions import core_action, live_profile, wired_actions
from scripts.evaluator.strategies import (
    ActionCandidate,
    bounded_random_action,
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
        LiveActionContract(
            backend="owned_route_re_entry_v1",
            action="re_entry",
            boundary_prefix="re_entry_offset",
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


CORPUS_SCHEMA = "2.0"


def enabled_corpus_candidates(
    *,
    mechanism: str,
    corpus: tuple[str, ...],
    timing_bounds_ns: dict[str, list[int]],
) -> list[dict[str, Any]]:
    """Every (action, timing boundary) the grammar permits for this mechanism.

    An action is only offered when a live backend can apply it for the given
    mechanism, so an unsupported combination cannot be selected rather than
    being selected and failing later.
    """

    wired = {action.action_id for action in wired_actions(mechanism)}
    candidates: list[dict[str, Any]] = []
    for action_id in corpus:
        action = core_action(action_id)
        bounds = timing_bounds_ns.get(action_id)
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise LiveStrategyError(f"{action_id} timing bounds are required")
        lower, upper = bounds
        if not all(isinstance(value, int) for value in bounds) or lower < 0 or upper < lower:
            raise LiveStrategyError(f"{action_id} timing bounds are invalid")
        for boundary, offset in OFFSETS_NS:
            candidates.append(
                {
                    "action": action_id,
                    "backend": action.backend,
                    "boundary": boundary,
                    "offset_ns": offset,
                    "unit": f"{action_id}:{boundary}",
                    "required_state": sorted(action.live_markers),
                    "timing_anchor": (
                        action.live_profile.timing_anchor
                        if action.live_profile is not None
                        else None
                    ),
                    "enabled": action_id in wired and lower <= offset <= upper,
                }
            )
    return candidates


def _derived_seed(seed: int, label: str) -> int:
    """A reproducible sub-seed so the action and timing draws stay independent.

    Reusing one seed for both would make timing a function of the seed alone,
    and a campaign would then explore a correlated slice of the joint space
    instead of the space itself.
    """

    material = json.dumps(
        {"seed": seed, "label": label}, sort_keys=True, separators=(",", ":")
    ).encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def create_corpus_decision(
    *,
    strategy: str,
    seed: int | None,
    mechanism: str,
    corpus: tuple[str, ...],
    timing_bounds_ns: dict[str, list[int]],
    official_action: str,
    official_offset_ns: int,
    covered_units: set[str],
) -> dict[str, Any]:
    """Select one action and one timing from the declared corpus.

    This is the Stage 2 decision surface: the policy chooses which action to
    apply, not only when to apply a preconfigured one.  The decision remains a
    pure function of its inputs so the container can re-derive and compare it.
    """

    if strategy not in SUPPORTED_STRATEGIES:
        raise LiveStrategyError(f"unsupported live strategy: {strategy}")
    if not corpus:
        raise LiveStrategyError("a corpus decision needs at least one declared action")
    if not isinstance(official_offset_ns, int):
        raise LiveStrategyError("official action offset must be an integer")
    if not all(isinstance(item, str) for item in covered_units):
        raise LiveStrategyError("covered units must be strings")
    candidates = enabled_corpus_candidates(
        mechanism=mechanism, corpus=corpus, timing_bounds_ns=timing_bounds_ns
    )
    enabled = [item for item in candidates if item["enabled"]]
    if not enabled:
        raise LiveStrategyError("no corpus candidate is executable for this mechanism")

    if strategy == "official_sequence":
        if seed is not None:
            raise LiveStrategyError("official sequence must not use a strategy seed")
        official_sequence([official_action])
        selected = next(
            (
                item
                for item in enabled
                if item["action"] == official_action
                and item["offset_ns"] == official_offset_ns
            ),
            None,
        )
        if selected is None:
            raise LiveStrategyError("the official action and offset are not executable")
    elif strategy == "bounded_random_timing":
        if seed is None:
            raise LiveStrategyError("bounded random timing requires a seed")
        action = bounded_random_action(
            {item["action"] for item in enabled}, seed=seed
        )
        bounds = timing_bounds_ns[action]
        offset = int(
            bounded_random_timing(
                [action], {action: bounds}, seed=_derived_seed(seed, action)
            )[0]["delay_ns"]
        )
        boundary = boundary_for_offset(offset)
        selected = next(
            item
            for item in enabled
            if item["action"] == action and item["boundary"] == boundary
        )
    else:
        if seed is None:
            raise LiveStrategyError("state-aware selection requires a seed")
        planned_state = {
            marker: True
            for item in enabled
            for marker in item["required_state"]
        }
        candidate = choose_state_aware(
            [
                ActionCandidate(
                    name=item["unit"],
                    required_state=tuple(
                        sorted((marker, True) for marker in item["required_state"])
                    ),
                    covers=(item["unit"],),
                    deadline_distance_ns=item["offset_ns"] - official_offset_ns,
                )
                for item in enabled
            ],
            state=planned_state,
            covered_contract_boundaries=covered_units,
            seed=seed,
        )
        selected = next(item for item in enabled if item["unit"] == candidate.name)

    return {
        "schema_version": CORPUS_SCHEMA,
        "strategy": strategy,
        "seed": seed,
        "mechanism": mechanism,
        "corpus": list(corpus),
        "action": selected["action"],
        "backend": selected["backend"],
        "required_state": selected["required_state"],
        "timing_anchor": live_profile(selected["action"]).timing_anchor,
        "timing_bounds_ns": dict(sorted(timing_bounds_ns.items())),
        "official_action": official_action,
        "official_offset_ns": official_offset_ns,
        "planned_offset_ns": selected["offset_ns"],
        "selected_boundary": selected["boundary"],
        "selected_unit": selected["unit"],
        "covered_units_before_decision": sorted(covered_units),
        "candidates": candidates,
    }


def validate_corpus_decision(value: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "strategy",
        "seed",
        "mechanism",
        "corpus",
        "action",
        "backend",
        "required_state",
        "timing_anchor",
        "timing_bounds_ns",
        "official_action",
        "official_offset_ns",
        "planned_offset_ns",
        "selected_boundary",
        "selected_unit",
        "covered_units_before_decision",
        "candidates",
    }
    if set(value) != required:
        raise LiveStrategyError("corpus decision shape differs")
    covered = value.get("covered_units_before_decision")
    if not isinstance(covered, list) or not all(isinstance(item, str) for item in covered):
        raise LiveStrategyError("corpus coverage feedback is invalid")
    corpus = value.get("corpus")
    if not isinstance(corpus, list) or not all(isinstance(item, str) for item in corpus):
        raise LiveStrategyError("corpus decision names an invalid corpus")
    expected = create_corpus_decision(
        strategy=str(value.get("strategy")),
        seed=value.get("seed"),
        mechanism=str(value.get("mechanism")),
        corpus=tuple(corpus),
        timing_bounds_ns=value.get("timing_bounds_ns"),
        official_action=str(value.get("official_action")),
        official_offset_ns=value.get("official_offset_ns"),
        covered_units=set(covered),
    )
    if value != expected:
        raise LiveStrategyError("corpus decision differs from the registered contract")


def validate_live_decision(value: dict[str, Any]) -> None:
    if not isinstance(value, dict):
        raise LiveStrategyError("live strategy decision is not an object")
    if value.get("schema_version") == CORPUS_SCHEMA:
        validate_corpus_decision(value)
        return
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
