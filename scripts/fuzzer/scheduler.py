"""Deterministic random and state-aware Fuzzer v0 scheduling."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any

from .mutators import MutationResult, mutate


@dataclass(frozen=True)
class ScheduledCase:
    parent_case_id: str
    strategy: str
    rng_seed: int
    mutation: MutationResult


def schedule_random(seeds: list[dict[str, Any]], *, rng_seed: int) -> ScheduledCase:
    rng = random.Random(rng_seed)
    parent = rng.choice(sorted(seeds, key=lambda item: item["case_id"]))
    mutation_seed = rng.randrange(0, 2**31)
    return ScheduledCase(parent["case_id"], "random_baseline", mutation_seed, mutate(parent, rng_seed=mutation_seed))


def schedule_guided(
    seeds: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    rng_seed: int,
) -> ScheduledCase:
    scores: dict[str, tuple[float, float, str]] = {
        seed["case_id"]: (0.0, 0.0, seed["case_id"]) for seed in seeds
    }
    for result in history:
        parent = result.get("parent_case_id")
        if parent not in scores:
            continue
        tier = float(result.get("fitness", {}).get("validity_tier", 0))
        novelty = float(result.get("novelty", {}).get("route_state", 0)) + float(
            result.get("novelty", {}).get("transition_sequence", 0)
        )
        total = float(result.get("fitness", {}).get("total", 0))
        scores[parent] = max(scores[parent], (tier + novelty, total, parent))
    parent_id = max(scores, key=lambda item: scores[item])
    parent = next(seed for seed in seeds if seed["case_id"] == parent_id)
    mutation_seed = random.Random(rng_seed).randrange(0, 2**31)
    return ScheduledCase(parent_id, "state_aware_guided", mutation_seed, mutate(parent, rng_seed=mutation_seed))
