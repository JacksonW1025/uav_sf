import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_measurement_gate_is_complete_and_unblocked() -> None:
    gate = _load("experiments/motivation/phase_a2_measurement_gate.json")
    assert gate["status"] == "PASS"
    assert gate["selected_uorb_queue_length"] == 4
    assert gate["blocking_items"] == []
    assert set(gate["criteria"]) == {f"M{index}" for index in range(1, 12)}
    assert all(item["status"] == "PASS" for item in gate["criteria"].values())


def test_reentry_gate_matches_all_three_processed_results() -> None:
    gate = _load("experiments/motivation/phase_a2_reentry_gate.json")
    d0 = _load(
        "data/processed/p0d0/p0d0_internal_rearm_r4_20260717/route_summary.json"
    )
    d1 = _load(
        "data/processed/p0d1/p0d1_lifecycle_r2_20260717/registration_lifecycle_result.json"
    )
    d2 = _load(
        "data/processed/p0d2/p0d2_full_reentry_r3_20260717/reentry_result.json"
    )
    assert d0["baseline"]["status"] == "PASS"
    assert d1["status"] == "PASS"
    assert d2["status"] == "PASS"
    assert d2["conclusion"] == "clean_reentry"
    assert gate["status"] == "PASS"
    assert all(item["status"] == "PASS" for item in gate["criteria"].values())
