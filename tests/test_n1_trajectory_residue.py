import time
from pathlib import Path

import yaml

from scripts.probes.inject_n1_trajectory_fault import PHASE_OFFSETS_SECONDS, next_health_reply


ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION = (
    ROOT / "experiments/motivation/n1_trajectory_residue/preregistration.yaml"
)
MATRIX = ROOT / "experiments/motivation/n1_trajectory_residue/matrix.yaml"
LEDGER = ROOT / "experiments/motivation/n1_trajectory_residue/attempt_ledger.yaml"
RUNNER = ROOT / "scripts/probes/run_n1_trajectory_residue.sh"


def test_n1_preregistration_is_bounded_and_preserves_f1_context() -> None:
    record = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    assert record["status"] == "FROZEN_BEFORE_FORMAL_ATTEMPTS"
    assert record["source_revisions"]["px4_autopilot"] == (
        "4ae21a5e569d3d89c2f6366688cbacb3e93437c9"
    )
    assert record["source_revisions"]["px4_ros2_interface_lib"] == (
        "c3e410f035806e8c56246708432ded09c976434b"
    )
    assert record["scenario"]["setpoint_type"] == "TRAJECTORY"
    assert record["scenario"]["trajectory_velocity_m_s"] == [0.5, 0.0, 0.0]
    assert record["scenario"]["expected_fallback"] == "AUTO_RTL_nav_state_5"
    assert record["formal_matrix"]["accepted_runs_per_bucket"] == 3
    assert record["formal_matrix"]["maximum_attempts_per_bucket"] == 6
    assert record["formal_matrix"]["maximum_total_attempts"] == 18
    assert record["reproduction_rule"]["reduced_observation_confirmation_maximum_attempts"] == 3


def test_n1_phase_buckets_cover_one_health_interval_without_state_mutation() -> None:
    record = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    buckets = record["phase_buckets"]
    assert PHASE_OFFSETS_SECONDS == {"A": 0.03, "B": 0.15, "C": 0.26}
    assert buckets["health_request_interval_ms"] == 300
    assert [buckets[name]["requested_offset_ms"] for name in ("A", "B", "C")] == [
        30,
        150,
        260,
    ]
    assert buckets["direct_health_state_mutation"] == "FORBIDDEN"
    runner = RUNNER.read_text(encoding="utf-8")
    assert 'PHASE_BUCKET="${N1_HEALTH_PHASE_BUCKET:?N1_HEALTH_PHASE_BUCKET is required}"' in runner
    assert '--phase-bucket "${PHASE_BUCKET}"' in runner
    assert '--health-log "${RAW_DIR}/external_mode.log"' in runner


def test_n1_health_cycle_anchor_reads_only_appended_reply(tmp_path: Path) -> None:
    health_log = tmp_path / "external_mode.log"
    health_log.write_text(
        '[INFO] {"event_type":"freshness_health_reply","sequence":3,"ros_time_ns":10}\n',
        encoding="utf-8",
    )
    offset = health_log.stat().st_size
    with health_log.open("a", encoding="utf-8") as handle:
        handle.write(
            '[INFO] {"event_type":"freshness_health_reply","sequence":4,"ros_time_ns":20}\n'
        )
    record, observed_ns, final_offset = next_health_reply(
        health_log, offset, time.monotonic() + 0.5
    )
    assert record["sequence"] == 4
    assert observed_ns > 0
    assert final_offset == health_log.stat().st_size


def test_n1_matrix_and_ledger_match_preregistration_and_attempt_caps() -> None:
    matrix = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    ledger = yaml.safe_load(LEDGER.read_text(encoding="utf-8"))
    assert matrix["accepted_target"] == 9
    assert matrix["maximum_total_attempts"] == 18
    assert len(matrix["cells"]) == 3
    assert sum(cell["accepted_runs_required"] for cell in matrix["cells"]) == 9
    assert sum(cell["maximum_attempts"] for cell in matrix["cells"]) == 18
    attempts = ledger["attempts"]
    accepted = [item for item in attempts if item["counted_as_accepted"]]
    assert ledger["accepted_runs"] == matrix["accepted_runs"] == len(accepted)
    assert ledger["total_attempts"] == matrix["total_attempts"] == len(attempts)
    assert len({item["run_id"] for item in attempts}) == len(attempts)
    assert ledger["total_attempts"] <= matrix["maximum_total_attempts"]

    allowed_dispositions = {
        "ACCEPTED",
        "OBSERVABILITY_REJECTED",
        "MEASUREMENT_INSUFFICIENT",
        "ENVIRONMENT_FAILURE",
        "CAMPAIGN_CONFIGURATION_FAILURE",
        "FORMAL_SAFETY_STOP",
        "NOT_APPLICABLE",
    }
    assert {item["disposition"] for item in attempts} <= allowed_dispositions
    assert all(
        item["disposition"] == "ACCEPTED" for item in accepted
    )

    attempts_by_cell = {
        cell["cell_id"]: [
            item for item in attempts if item["cell_id"] == cell["cell_id"]
        ]
        for cell in matrix["cells"]
    }
    for cell in matrix["cells"]:
        cell_attempts = attempts_by_cell[cell["cell_id"]]
        cell_accepted = [item for item in cell_attempts if item["counted_as_accepted"]]
        assert cell["attempts"] == len(cell_attempts)
        assert cell["accepted_runs"] == len(cell_accepted)
        assert cell["attempts"] <= cell["maximum_attempts"]
        assert cell["accepted_runs"] <= cell["accepted_runs_required"]

    assert ledger["observability_rejections"] == sum(
        item["disposition"] == "OBSERVABILITY_REJECTED" for item in attempts
    )
    assert ledger["environment_failures"] == sum(
        item["disposition"] == "ENVIRONMENT_FAILURE" for item in attempts
    )


def test_n1_dispositions_are_closed_and_no_fuzzer_is_authorized() -> None:
    record = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    assert record["final_dispositions"] == [
        "CONFIRMED_REPRODUCIBLE_CURRENT_ROUTE_VIOLATION",
        "CURRENT_EVENT_REOBSERVED_BUT_PHASE_DEPENDENT",
        "NONREPRODUCED_BOUNDED_CURRENT_EVENT",
        "OBSERVATION_LINEAGE_ARTIFACT",
        "MEASUREMENT_INSUFFICIENT",
        "ENVIRONMENT_BLOCKED",
    ]
    assert "full_stateful_fuzzer_campaign" in record["scope_exclusions"]
