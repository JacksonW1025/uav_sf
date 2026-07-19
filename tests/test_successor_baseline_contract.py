from pathlib import Path

from scripts.analysis.classify_successor_baseline import attempt_classification


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "scripts"
    / "adapters"
    / "external_mode_adapter"
    / "src"
    / "successor_baseline.cpp"
).read_text(encoding="utf-8")
CMAKE = (
    ROOT / "scripts" / "adapters" / "external_mode_adapter" / "CMakeLists.txt"
).read_text(encoding="utf-8")
RUNNER = (ROOT / "scripts" / "probes" / "run_successor_baseline.sh").read_text(
    encoding="utf-8"
)


def test_baseline_is_isolated_nonreplacement_mode() -> None:
    assert 'Settings{kComponentName}.preventArming(false)' in SOURCE
    assert "replaceInternalMode" not in SOURCE
    assert 'constexpr const char* kComponentName = "Successor Baseline"' in SOURCE
    assert "UAV_SF_SUCCESSOR_ACTIVE_DURATION_S" in SOURCE


def test_baseline_executor_has_preregistered_successor_chain() -> None:
    stages = (
        '"stage\\\":\\\"wait_ready_to_arm',
        'log("executor_transition", "arm")',
        'log("executor_transition", "takeoff")',
        'log("executor_transition", "successor_baseline_external_mode")',
        'log("executor_transition", "land")',
        'log("executor_transition", "wait_until_disarmed")',
    )
    positions = [SOURCE.index(stage) for stage in stages]
    assert positions == sorted(positions)
    assert "scheduleMode(ownedMode().id()" in SOURCE
    assert "land([this]" in SOURCE
    assert "rtl(" not in SOURCE
    assert "waitUntilDisarmed" in SOURCE
    assert 'requireSuccess("external_mode_complete"' in SOURCE


def test_baseline_emits_oracle_lifecycle_contract() -> None:
    for event_type in (
        "mode_executor_registered",
        "executor_activated",
        "external_mode_activated",
        "external_mode_setpoint",
        "external_mode_completed",
        "external_mode_deactivated",
        "executor_result",
        "executor_transition",
    ):
        assert event_type in SOURCE
    assert "executor_id" in SOURCE
    assert "owned_mode" in SOURCE
    assert "registration_instance_id" in SOURCE
    assert "successor_baseline_executor" in CMAKE


def test_runner_is_bounded_and_keeps_p5_v6_isolated() -> None:
    assert "runs/motivation/successor/baseline" in RUNNER
    assert "data/processed/motivation/successor/baseline" in RUNNER
    assert "successor_lifecycle_monitor.py" in RUNNER
    assert RUNNER.index("successor_lifecycle_monitor.py") < RUNNER.index(
        'UAV_SF_SUCCESSOR_ACTIVE_DURATION_S="${ACTIVE_DURATION_S}"'
    )
    assert "--transition-target-mode 18" in RUNNER
    assert "successor_progression_oracle.py" in RUNNER
    assert "classify_successor_baseline.py" in RUNNER
    assert '--post-disarm-capture 8' in RUNNER
    assert '--abort-marker "${ABORT_MARKER}"' in RUNNER
    assert '--px4-early-exit "${PX4_EARLY_EXIT}"' in RUNNER
    assert "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc" in RUNNER
    assert "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518" in RUNNER
    assert "P5_RUN_ROOT" not in RUNNER


def test_infrastructure_abort_cannot_be_classified_as_oracle_violation() -> None:
    assert attempt_classification(False, True) == "ENVIRONMENT_FAILURE"
    assert attempt_classification(False, False) == "EVIDENCE_OR_ORACLE_FAILURE"
    assert attempt_classification(True, False) == "ACCEPTED_BASELINE"
