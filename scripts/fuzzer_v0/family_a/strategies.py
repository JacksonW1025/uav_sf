#!/usr/bin/env python3
"""Shared, frozen infrastructure for the three unauthorized comparison arms."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
FAMILY = ROOT / "experiments/fuzzer_v0/family_a"
STRATEGIES = {
    "OFFICIAL_SEQUENCE": {"arm": "V0-A", "rng_seed": None},
    "BOUNDED_RANDOM_TIMING_COMPARATOR": {"arm": "V0-B", "rng_seed": 2026072202},
    "STATE_AWARE_MUTATION": {"arm": "V0-C", "rng_seed": 2026072203},
}
ARM_BUDGET = 12
STATE_AWARE_TIERS = (
    (
        "new_admissible_route_lifecycle_freshness_state",
        "new_route_epoch_transition",
        "new_Oracle_applicability_combination",
        "new_owner_health_setpoint_failsafe_combination",
    ),
    (
        "new_event_ordering",
        "new_command_age_bucket",
        "new_vehicle_state_context",
        "new_accepted_evidence_signature",
    ),
    (
        "previously_reached_state_with_lower_reproduction_count",
        "N1_like_late_phase_window",
        "benchmark_compatible_condition",
    ),
)


class StrategyError(RuntimeError):
    """A comparison strategy request violates its frozen contract."""


@dataclass(frozen=True)
class TestCase:
    case_id: str
    seed_id: str
    mechanism: str
    source_route: str
    target_route: str
    setpoint_level: str
    applicable_oracles: tuple[str, ...]
    mutation_operator: str | None = None
    mutation_parameters: tuple[tuple[str, Any], ...] = ()
    simulation_seed: int = 0

    def canonical(self) -> dict[str, Any]:
        value = asdict(self)
        value["applicable_oracles"] = list(self.applicable_oracles)
        value["mutation_parameters"] = [list(item) for item in self.mutation_parameters]
        return value


def frozen_seed_pool() -> list[TestCase]:
    with (FAMILY / "seed_catalog.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    accepted = [
        row
        for row in rows
        if row["inclusion_status"] == "ACCEPTED_RUNTIME_SEED"
        and row["current_or_historical"] == "CURRENT"
        and row["runtime_or_replay"] == "RUNTIME"
    ]
    if len(rows) != 61 or len(accepted) != 50:
        raise StrategyError("frozen seed accounting changed")
    return [
        TestCase(
            case_id=f"seed:{row['seed_id']}",
            seed_id=row["seed_id"],
            mechanism=row["mechanism"],
            source_route=row["source_route"],
            target_route=row["target_or_retained_route"],
            setpoint_level=row["setpoint_level"],
            applicable_oracles=tuple(row["applicable_oracles"].split("|")),
        )
        for row in sorted(accepted, key=lambda item: item["seed_id"])
    ]


def official_sequence(slot: int) -> TestCase:
    pool = frozen_seed_pool()
    if not 0 <= slot < ARM_BUDGET:
        raise StrategyError("Official Sequence slot exceeds its budget")
    return pool[slot % len(pool)]


def bounded_random_sequence(candidates: Iterable[TestCase]) -> list[TestCase]:
    materialized = list(candidates)
    if not materialized:
        raise StrategyError("bounded random sample space is empty")
    generator = random.Random(2026072202)
    order = list(range(len(materialized)))
    generator.shuffle(order)
    selected = [materialized[index] for index in order[:ARM_BUDGET]]
    while len(selected) < ARM_BUDGET:
        selected.append(materialized[generator.randrange(len(materialized))])
    return selected


def state_aware_score(candidate: dict[str, Any]) -> tuple[Any, ...]:
    tiers = tuple(
        tuple(0 if bool(candidate.get(key)) else 1 for key in tier)
        for tier in STATE_AWARE_TIERS
    )
    realism = {"R1": 0, "R2": 1, "R3": 2}.get(
        str(candidate.get("realism_level")), 3
    )
    distance = int(candidate.get("reality_distance", 7))
    prior = int(candidate.get("prior_formal_executions", 0))
    stable_tie = int.from_bytes(
        hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).digest()[:8],
        "big",
    ) ^ 2026072203
    return (*tiers, realism, distance, prior, stable_tie)


def choose_state_aware(candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = list(candidates)
    if not values:
        raise StrategyError("state-aware candidate set is empty")
    return min(values, key=state_aware_score)


def finding_signature(record: dict[str, Any]) -> str:
    frozen_fields = {
        "source_route": record.get("source_route"),
        "target_route": record.get("target_route"),
        "route_epoch_transition": record.get("route_epoch_transition"),
        "lifecycle_edge": record.get("lifecycle_edge"),
        "oracle_results": record.get("oracle_results"),
        "classification": record.get("classification"),
    }
    return hashlib.sha256(
        json.dumps(frozen_fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def deduplicate(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(finding_signature(record), []).append(record)
    return groups


def write_coverage_state(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_arm_ledgers(ledgers: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    if set(ledgers) != set(STRATEGIES):
        raise StrategyError("comparison arm ledgers must remain separate")
    counts = {strategy: len(records) for strategy, records in ledgers.items()}
    if any(count > ARM_BUDGET for count in counts.values()):
        raise StrategyError("comparison arm budget exceeded")
    return counts


def require_comparison_authorization(
    decision: dict[str, Any], strategy: str
) -> None:
    if strategy not in STRATEGIES:
        raise StrategyError(f"unknown comparison strategy: {strategy}")
    field = {
        "OFFICIAL_SEQUENCE": "official_sequence_authorized",
        "BOUNDED_RANDOM_TIMING_COMPARATOR": "bounded_random_timing_authorized",
        "STATE_AWARE_MUTATION": "state_aware_authorized",
    }[strategy]
    if (
        decision.get("authorized_scope") == "V0_P_QUALIFICATION_ONLY"
        or decision.get("comparison_runtime_authorized") is not True
        or decision.get(field) is not True
    ):
        raise StrategyError(
            "qualification authorization cannot invoke a comparison strategy"
        )
