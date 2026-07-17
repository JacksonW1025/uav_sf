from __future__ import annotations

from scripts.fuzzer.case_model import validate_case
from scripts.fuzzer.minimize import minimize_case
from scripts.fuzzer.seed_loader import load_seeds


def test_minimizer_removes_unrelated_events_but_preserves_target_fault() -> None:
    case = next(seed for seed in load_seeds() if seed["case_id"] == "p2-dynamic-sigkill")
    case["transition_events"].insert(
        0, {"event_id": "unrelated", "kind": "cancel", "offset_s": 1.0}
    )
    validate_case(case)

    def preserves(candidate):
        return any(event["kind"] == "process_sigkill" for event in candidate["transition_events"])

    result = minimize_case(case, preserves_violation=preserves, budget=10)
    validate_case(result.case)
    assert not any(event["event_id"] == "unrelated" for event in result.case["transition_events"])
    assert any(event["kind"] == "process_sigkill" for event in result.case["transition_events"])
    assert result.accepted_reductions >= 1


def test_minimizer_respects_budget_and_rejects_unknown_equivalent() -> None:
    case = next(seed for seed in load_seeds() if seed["case_id"] == "p2-offboard-sigterm")
    result = minimize_case(case, preserves_violation=lambda _candidate: False, budget=2)
    assert result.evaluations <= 2
    assert result.accepted_reductions == 0
    assert result.case == case
