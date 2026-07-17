from __future__ import annotations

import pytest

from scripts.fuzzer.fitness import calculate_fitness
from scripts.fuzzer.validity import REQUIRED_CHECKS, classify_with_oracle


def checks():
    return {name: "PASS" for name in REQUIRED_CHECKS}


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ({"armed": "FAIL"}, "INVALID_SETUP"),
        ({"fault_delivered": "FAIL"}, "INVALID_SETUP"),
        ({"px4_alive": "FAIL"}, "ENVIRONMENT_FAILURE"),
        ({"gazebo_alive": "FAIL"}, "ENVIRONMENT_FAILURE"),
        ({"ulog_produced": "FAIL"}, "ENVIRONMENT_FAILURE"),
        ({"clock_bridge": "FAIL"}, "MEASUREMENT_UNKNOWN"),
        ({"critical_window": "FAIL"}, "MEASUREMENT_UNKNOWN"),
    ],
)
def test_validity_classifier_never_promotes_failed_evidence(changed, expected) -> None:
    evidence = checks()
    evidence.update(changed)
    classification, _ = classify_with_oracle(evidence, {"status": "VIOLATION", "clauses": {}})
    assert classification == expected


def test_complete_oracle_pass_and_violation_are_distinguished() -> None:
    passed, _ = classify_with_oracle(checks(), {"status": "PASS", "clauses": {}})
    violated, _ = classify_with_oracle(
        checks(),
        {"status": "VIOLATION", "clauses": {"revocation": {"status": "VIOLATION"}}},
    )
    unknown, _ = classify_with_oracle(checks(), {"status": "UNKNOWN", "clauses": {}})
    assert (passed, violated, unknown) == ("SUT_PASS", "SUT_VIOLATION", "MEASUREMENT_UNKNOWN")


def test_environment_failure_cannot_receive_positive_fitness() -> None:
    environment = calculate_fitness(
        "ENVIRONMENT_FAILURE",
        clause_metrics=[{"status": "VIOLATION", "value": 100, "threshold": 1, "uncertainty": 0}],
        route_state_novelty=1,
        sequence_novelty=1,
        physical_severity=1,
    )
    violation = calculate_fitness(
        "SUT_VIOLATION",
        clause_metrics=[{"status": "VIOLATION", "value": 2, "threshold": 1, "uncertainty": 0}],
    )
    assert environment["validity_tier"] == 0
    assert environment["total"] < 0 < violation["total"]
