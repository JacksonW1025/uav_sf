from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments" / "motivation" / "freshness"


def _load(name: str) -> dict[str, object]:
    value = yaml.safe_load((BASE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_primary_preregistration_locks_current_harness_and_protected_evidence() -> None:
    profile = _load("primary_preregistration.yaml")
    assert profile["status"] == "FROZEN_BEFORE_FORMAL_PILOT"
    assert profile["source_revisions"]["repository_harness_commit"] == (
        "2a03682d37499eb6eb96d0838891e09908637b9b"
    )
    for artifact in profile["locked_artifacts"]:
        assert _sha256(ROOT / artifact["path"]) == artifact["sha256"]

    missing_local_binaries = []
    for artifact in profile["locked_binaries"].values():
        path = ROOT / artifact["path"]
        if not path.is_file():
            missing_local_binaries.append(artifact["path"])
            continue
        assert _sha256(path) == artifact["sha256"]
    for evidence in profile["protected_evidence"].values():
        assert _sha256(ROOT / evidence["path"]) == evidence["sha256"]

    if missing_local_binaries:
        pytest.skip(
            "locked local runtime binaries are intentionally absent from a clean "
            "checkout; formal Freshness preflight required all binaries: "
            + ", ".join(missing_local_binaries)
        )


def test_formal_matrix_is_exactly_four_cells_and_twelve_accepted_runs() -> None:
    profile = _load("primary_preregistration.yaml")
    matrix = _load("pilot_matrix.yaml")
    cells = profile["formal_cells"]
    assert [(cell["cell_id"], cell["setpoint_type"], cell["fault_type"]) for cell in cells] == [
        ("F1", "TRAJECTORY", "TOTAL_PROCESS_STOP"),
        ("F2", "ATTITUDE", "TOTAL_PROCESS_STOP"),
        ("F3", "RATE", "TOTAL_PROCESS_STOP"),
        ("F4", "RATE", "SETPOINT_ONLY_STALL"),
    ]
    assert all(cell["accepted_runs_required"] == 3 for cell in cells)
    assert all(cell["maximum_total_attempts"] == 6 for cell in cells)
    assert matrix["accepted_runs_target"] == 12
    assert matrix["maximum_total_accepted_runs"] == 12
    assert len(matrix["cells"]) == 4
    assert all(len(cell["attempt_slots"]) == 6 for cell in matrix["cells"])


def test_rate_differential_changes_only_failure_condition() -> None:
    matrix = _load("pilot_matrix.yaml")
    f3, f4 = (next(cell for cell in matrix["cells"] if cell["cell_id"] == name) for name in ("F3", "F4"))
    for field in ("setpoint_type", "setpoint", "stable_seconds", "target_seconds", "recovery_seconds"):
        assert f3[field] == f4[field]
    assert f3["fault_type"] == "TOTAL_PROCESS_STOP"
    assert f4["fault_type"] == "SETPOINT_ONLY_STALL"
    assert [slot["seed"] for slot in f3["attempt_slots"]] == [
        slot["seed"] for slot in f4["attempt_slots"]
    ]


def test_policy_interpretation_and_ledger_aggregates_are_consistent() -> None:
    profile = _load("primary_preregistration.yaml")
    ledger = _load("attempt_ledger.yaml")
    assert profile["policy"]["freshness"] == "NONE"
    assert profile["policy"]["setpoint_timeout_ms"] is None
    assert profile["timing"]["setpoint_only_stall_target_seconds_monotonic"] == 3.0
    assert profile["interpretation_rules"]["route_oracle_rule"] == (
        "Route Oracle PASS does not erase a Freshness exposure."
    )
    assert ledger["preregistration_commit"] == "be11b984e13c9df43ebc8b3b31d04517c46d5224"
    assert ledger["accepted_runs"] == sum(
        int(cell["accepted_runs"]) for cell in ledger["cell_counts"].values()
    )
    assert ledger["total_attempts"] == len(ledger["attempts"])
    assert all(
        int(cell["total_attempts"]) <= int(cell["maximum_total_attempts"])
        for cell in ledger["cell_counts"].values()
    )
