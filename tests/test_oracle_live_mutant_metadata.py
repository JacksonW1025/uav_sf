from __future__ import annotations

from pathlib import Path

from scripts.oracles.oracle_live_validation import expected_assertions, load_matrix


ROOT = Path(__file__).resolve().parents[1]


def test_live_mutants_are_isolated_marked_and_preregistered() -> None:
    patch = (
        ROOT
        / "patches"
        / "px4"
        / "oracle_validation_mutants"
        / "mc_pos_control_route_mutants.patch"
    ).read_text(encoding="utf-8")
    assert "TEST-ONLY ORACLE VALIDATION MUTANT" in patch
    assert "DO NOT USE AS CANONICAL SUT" in patch
    build = (ROOT / "scripts" / "setup" / "build_oracle_mutant.sh").read_text(
        encoding="utf-8"
    )
    assert "PX4-Autopilot-oracle-validation-mutant" in build
    assert "PX4-Autopilot-route-observability-q4-transition/build" not in build

    rows = load_matrix()
    assert len([row for row in rows if row["mutant_type"] == "control"]) == 3
    for mutant_type in (
        "install_delay",
        "recovery_incomplete",
        "old_route_late_consumption",
    ):
        matching = [row for row in rows if row["mutant_type"] == mutant_type]
        assert len(matching) >= 3
        assert all(expected_assertions(row) for row in matching)
    assert {
        int(row["delay_ms"])
        for row in rows
        if row["mutant_type"] == "install_delay"
    } == {200, 500, 1000}
