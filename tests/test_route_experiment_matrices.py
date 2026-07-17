from pathlib import Path

from scripts.analysis.build_route_experiment_matrix import build


ROOT = Path(__file__).resolve().parents[1]


def test_p2_processed_matrix_has_eighteen_accepted_cases() -> None:
    columns, rows = build("p2", ROOT / "data/processed/p2")
    assert len(rows) == 18
    assert "fault_class" in columns


def test_p3_processed_matrix_has_twenty_four_accepted_cases() -> None:
    columns, rows = build("p3", ROOT / "data/processed/p3")
    assert len(rows) == 24
    assert "heartbeat_or_health_enabled" in columns
