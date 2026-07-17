"""Deterministic clause-preserving delta minimization for Fuzzer v0."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from .case_model import SemanticCaseError, case_digest, validate_case


Predicate = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class MinimizationResult:
    case: dict[str, Any]
    evaluations: int
    accepted_reductions: int
    budget_exhausted: bool


def _candidate(case: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(case)
    result["case_id"] = f"min-{case_digest(result)[:16]}"
    return result


def reduction_candidates(case: dict[str, Any]) -> Iterator[dict[str, Any]]:
    events = case["transition_events"]
    referenced = {fault["event_id"] for fault in case["faults"]}
    for index, event in enumerate(events):
        if len(events) <= 1 or event["event_id"] in referenced:
            continue
        reduced = copy.deepcopy(case)
        del reduced["transition_events"][index]
        yield _candidate(reduced)
    if case["faults"]:
        reduced = copy.deepcopy(case)
        fault_event = reduced["faults"][0]["event_id"]
        reduced["faults"] = []
        reduced["transition_events"] = [
            event for event in reduced["transition_events"] if event["event_id"] != fault_event
        ]
        if reduced["transition_events"]:
            yield _candidate(reduced)
    for index, event in enumerate(events):
        if float(event["offset_s"]) <= 0.0:
            continue
        reduced = copy.deepcopy(case)
        previous = float(events[index - 1]["offset_s"]) if index else 0.0
        reduced["transition_events"][index]["offset_s"] = round(
            previous + (float(event["offset_s"]) - previous) / 2.0, 3
        )
        reduced["timing"]["fault_offset_s"] = min(
            float(reduced["timing"]["fault_offset_s"]),
            float(reduced["transition_events"][index]["offset_s"]),
        )
        yield _candidate(reduced)
    if case["behavior_context"] != "hover":
        reduced = copy.deepcopy(case)
        reduced["behavior_context"] = "hover"
        reduced["initial_state_constraints"].update(
            {
                "maximum_speed_m_s": 0.5,
                "maximum_descent_rate_m_s": 0.1,
                "maximum_turn_rate_rad_s": 0.1,
            }
        )
        for event in reduced["transition_events"]:
            event.pop("condition", None)
        yield _candidate(reduced)
    if int(case["repetition"]["count"]) > 1:
        reduced = copy.deepcopy(case)
        reduced["repetition"]["count"] = 1
        yield _candidate(reduced)


def minimize_case(
    case: dict[str, Any], *, preserves_violation: Predicate, budget: int = 30
) -> MinimizationResult:
    if budget < 1:
        raise ValueError("minimization budget must be positive")
    current = copy.deepcopy(case)
    evaluations = 0
    accepted = 0
    changed = True
    while changed and evaluations < budget:
        changed = False
        for candidate in reduction_candidates(current):
            if evaluations >= budget:
                break
            try:
                validate_case(candidate)
            except SemanticCaseError:
                continue
            evaluations += 1
            if preserves_violation(candidate):
                current = candidate
                accepted += 1
                changed = True
                break
    return MinimizationResult(
        case=current,
        evaluations=evaluations,
        accepted_reductions=accepted,
        budget_exhausted=evaluations >= budget,
    )
