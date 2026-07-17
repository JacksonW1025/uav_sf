from __future__ import annotations

from scripts.fuzzer.replay import replay_candidate
from scripts.fuzzer.seed_loader import load_seeds


CASE = load_seeds()[0]


def result(classification, clauses=()):
    return {"classification": classification, "oracle": {"target_clauses": list(clauses)}}


def test_three_matching_replays_are_reproducible() -> None:
    summary = replay_candidate(
        CASE,
        target_clause="installation",
        evaluator=lambda _case, _attempt: result("SUT_VIOLATION", ["installation"]),
    )
    assert summary.status == "REPRODUCIBLE"
    assert summary.matching_clause_count == 3


def test_mixed_valid_replays_are_flaky() -> None:
    outcomes = [
        result("SUT_VIOLATION", ["continuity"]),
        result("SUT_PASS"),
        result("SUT_VIOLATION", ["continuity"]),
    ]
    summary = replay_candidate(
        CASE, target_clause="continuity", evaluator=lambda _case, attempt: outcomes[attempt - 1]
    )
    assert summary.status == "FLAKY"


def test_environment_failure_does_not_confirm_candidate() -> None:
    outcomes = [
        result("SUT_VIOLATION", ["revocation"]),
        result("ENVIRONMENT_FAILURE"),
        result("SUT_VIOLATION", ["revocation"]),
    ]
    summary = replay_candidate(
        CASE, target_clause="revocation", evaluator=lambda _case, attempt: outcomes[attempt - 1]
    )
    assert summary.status == "ENVIRONMENT_FAILURE"


def test_wrong_clause_is_not_reproduced() -> None:
    summary = replay_candidate(
        CASE,
        target_clause="recovery",
        evaluator=lambda _case, _attempt: result("SUT_VIOLATION", ["installation"]),
    )
    assert summary.status == "NOT_REPRODUCED"
