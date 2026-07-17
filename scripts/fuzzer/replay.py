"""Three-run reproduction for Fuzzer v0 violation candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


Evaluator = Callable[[dict[str, Any], int], dict[str, Any]]


@dataclass(frozen=True)
class ReplaySummary:
    status: str
    attempts: int
    matching_clause_count: int
    results: list[dict[str, Any]]


def _violates(result: dict[str, Any], target_clause: str) -> bool:
    return (
        result.get("classification") == "SUT_VIOLATION"
        and target_clause in result.get("oracle", {}).get("target_clauses", [])
    )


def replay_candidate(
    case: dict[str, Any],
    *,
    target_clause: str,
    evaluator: Evaluator,
    attempts: int = 3,
) -> ReplaySummary:
    if attempts != 3:
        raise ValueError("Fuzzer v0 candidate replay is frozen at exactly three attempts")
    results = [evaluator(case, index) for index in range(1, attempts + 1)]
    matching = sum(_violates(result, target_clause) for result in results)
    environment_failures = sum(
        result.get("classification") == "ENVIRONMENT_FAILURE" for result in results
    )
    valid = sum(
        result.get("classification") in {"SUT_PASS", "SUT_VIOLATION"} for result in results
    )
    if matching == attempts:
        status = "REPRODUCIBLE"
    elif environment_failures and valid < attempts:
        status = "ENVIRONMENT_FAILURE"
    elif matching:
        status = "FLAKY"
    else:
        status = "NOT_REPRODUCED"
    return ReplaySummary(status, attempts, matching, results)
