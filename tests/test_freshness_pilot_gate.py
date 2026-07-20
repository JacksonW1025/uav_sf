from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments" / "motivation" / "freshness"


def _yaml(name: str) -> dict[str, object]:
    value = yaml.safe_load((BASE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _gate() -> dict[str, object]:
    value = json.loads((BASE / "freshness_pilot_gate.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_final_gate_preserves_partial_matrix_and_attempt_accounting() -> None:
    gate = _gate()
    ledger = _yaml("attempt_ledger.yaml")
    matrix = _yaml("pilot_matrix.yaml")

    assert gate["final_disposition"] == "CURRENT_NATURAL_VIOLATION_FOUND"
    assert gate["execution"]["accepted_runs"] == ledger["accepted_runs"] == 10
    assert gate["execution"]["total_attempts"] == ledger["total_attempts"] == 16
    assert gate["execution"]["planned_accepted_runs"] == matrix["accepted_runs_target"] == 12
    assert gate["execution"]["matrix_status"] == "PARTIAL_AT_PREREGISTERED_ATTEMPT_LIMIT"
    assert gate["gate"]["measurement_insufficient_cells"] == ["F2"]
    assert gate["execution"]["no_further_formal_attempt_authorized"] is True


def test_accepted_oracle_counts_and_natural_violation_match_ledger() -> None:
    gate = _gate()
    ledger = _yaml("attempt_ledger.yaml")
    accepted = [attempt for attempt in ledger["attempts"] if attempt["counted_as_accepted"]]

    assert len(accepted) == 10
    assert sum(attempt["freshness_oracle"] == "EXPOSURE" for attempt in accepted) == 10
    assert sum(attempt["route_oracle"] == "PASS" for attempt in accepted) == 9
    violations = [attempt for attempt in accepted if attempt["route_oracle"] == "VIOLATION"]
    assert [attempt["run_id"] for attempt in violations] == ["freshness-f1-a02"]
    assert gate["natural_violation"]["run_id"] == violations[0]["run_id"]
    assert gate["natural_violation"]["post_revocation_stale_subject_consumption_count"] == 2
    assert gate["natural_violation"]["post_revocation_allocator_count"] == 0
    assert gate["natural_violation"]["post_revocation_writer_count"] == 0


def test_health_alive_cell_is_complete_and_differential_is_unchanged() -> None:
    gate = _gate()
    matrix = _yaml("pilot_matrix.yaml")
    f3 = next(cell for cell in matrix["cells"] if cell["cell_id"] == "F3")
    f4 = next(cell for cell in matrix["cells"] if cell["cell_id"] == "F4")

    assert f3["setpoint"] == f4["setpoint"]
    assert f3["stable_seconds"] == f4["stable_seconds"]
    assert f3["target_seconds"] == f4["target_seconds"] == 3.0
    assert gate["cells"]["F4"]["accepted_runs"] == 3
    assert gate["cells"]["F4"]["health_requests"] == 26
    assert gate["cells"]["F4"]["matched_health_replies"] == 26
    assert gate["cells"]["F4"]["external_route_retained_at_every_target_end"] is True
    assert gate["cells"]["F4"]["automatic_fallbacks_in_target_windows"] == 0


def test_final_report_exists_and_names_both_bounded_outcomes() -> None:
    report = (ROOT / "docs" / "motivation" / "SETPOINT_FRESHNESS_PILOT_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "CURRENT_NATURAL_VIOLATION_FOUND" in report
    assert "All 10 accepted runs return Freshness Oracle `EXPOSURE`" in report
    assert "F2 reached its six-attempt cap at `1/3`" in report
