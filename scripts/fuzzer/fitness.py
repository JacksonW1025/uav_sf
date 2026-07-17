"""Frozen, validity-tiered Fuzzer v0 fitness calculation."""

from __future__ import annotations

from typing import Any


VALIDITY_TIER = {
    "SUT_PASS": 3,
    "SUT_VIOLATION": 3,
    "VALID": 3,
    "MEASUREMENT_UNKNOWN": 2,
    "INVALID_INPUT": 1,
    "INVALID_SETUP": 1,
    "ENVIRONMENT_FAILURE": 0,
}
PENALTY = {
    "MEASUREMENT_UNKNOWN": 4.0,
    "INVALID_INPUT": 6.0,
    "INVALID_SETUP": 6.0,
    "ENVIRONMENT_FAILURE": 8.0,
}


def _normalized_excess(value: Any, threshold: Any, uncertainty: Any) -> float:
    try:
        numerator = float(value) - float(threshold) - float(uncertainty)
        denominator = max(abs(float(threshold)), 1.0)
    except (TypeError, ValueError):
        return 0.0
    return min(4.0, max(0.0, numerator / denominator))


def calculate_fitness(
    classification: str,
    *,
    clause_metrics: list[dict[str, Any]] | None = None,
    route_state_novelty: float = 0.0,
    sequence_novelty: float = 0.0,
    physical_severity: float = 0.0,
    duplicate: bool = False,
) -> dict[str, float | int]:
    tier = VALIDITY_TIER[classification]
    penalty = PENALTY.get(classification, 0.0) + (2.0 if duplicate else 0.0)
    if tier < 3:
        return {"validity_tier": tier, "total": -penalty, "contract_distance": 0.0, "penalty": penalty}
    metrics = clause_metrics or []
    distances = [
        _normalized_excess(item.get("value"), item.get("threshold"), item.get("uncertainty"))
        for item in metrics
    ]
    contract_distance = max(distances, default=0.0)
    violations = sum(item.get("status") == "VIOLATION" for item in metrics)
    novelty_a = min(1.0, max(0.0, route_state_novelty))
    novelty_b = min(1.0, max(0.0, sequence_novelty))
    severity = min(1.0, max(0.0, physical_severity))
    total = (
        10.0 * violations
        + 2.0 * contract_distance
        + novelty_a
        + 0.5 * novelty_b
        + 0.25 * severity
        - penalty
    )
    return {
        "validity_tier": tier,
        "total": total,
        "contract_distance": contract_distance,
        "penalty": penalty,
    }
