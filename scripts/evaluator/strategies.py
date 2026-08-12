#!/usr/bin/env python3
"""Controlled official, bounded-timing, and state-aware strategies."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any, Iterable


class StrategyError(ValueError):
    """A strategy request violates its preregistered bounds."""


def official_sequence(actions: Iterable[str]) -> list[dict[str, int | str]]:
    values = list(actions)
    if not values or any(not isinstance(action, str) or not action for action in values):
        raise StrategyError("official actions must be non-empty strings")
    return [{"action": action, "delay_ns": 0} for action in values]


def bounded_random_timing(
    actions: Iterable[str],
    bounds_ns: dict[str, list[int]],
    *,
    seed: int,
) -> list[dict[str, int | str]]:
    generator = random.Random(seed)
    scheduled: list[dict[str, int | str]] = []
    for action in actions:
        if action not in bounds_ns:
            raise StrategyError(f"missing timing bound for action: {action}")
        lower, upper = bounds_ns[action]
        if lower < 0 or upper < lower:
            raise StrategyError(f"invalid timing bound for action: {action}")
        scheduled.append({"action": action, "delay_ns": generator.randint(lower, upper)})
    return scheduled


@dataclass(frozen=True)
class ActionCandidate:
    name: str
    required_state: tuple[tuple[str, Any], ...]
    covers: tuple[str, ...]
    deadline_distance_ns: int
    safety_rank: int = 0

    def enabled(self, state: dict[str, Any]) -> bool:
        return all(state.get(name) == value for name, value in self.required_state)


def choose_state_aware(
    candidates: Iterable[ActionCandidate],
    *,
    state: dict[str, Any],
    covered_contract_boundaries: set[str],
    seed: int,
) -> ActionCandidate:
    enabled = [candidate for candidate in candidates if candidate.enabled(state)]
    if not enabled:
        raise StrategyError("no state-aware action satisfies its preconditions")

    def score(candidate: ActionCandidate) -> tuple[int, int, int, int]:
        uncovered = sum(
            boundary not in covered_contract_boundaries for boundary in candidate.covers
        )
        material = json.dumps(
            {"name": candidate.name, "state": state, "seed": seed},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        tie = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
        return (
            -uncovered,
            candidate.safety_rank,
            abs(candidate.deadline_distance_ns),
            tie,
        )

    return min(enabled, key=score)
