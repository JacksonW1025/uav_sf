import hashlib
import json
from pathlib import Path

from scripts.analysis.classify_successor_historical_replay import bridge_window, classify


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "scripts/adapters/external_mode_adapter/src/issue162_replay.cpp"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
PROVENANCE = json.loads(
    (
        ROOT
        / "experiments/motivation/successor/historical_replay_build_provenance.json"
    ).read_text(encoding="utf-8")
)
MONITOR = (ROOT / "scripts/tracing/successor_lifecycle_monitor.py").read_text(
    encoding="utf-8"
)
RUNNER = (ROOT / "scripts/probes/run_successor_historical_replay.sh").read_text(
    encoding="utf-8"
)


def test_historical_build_uses_preregistered_affected_stack() -> None:
    assert PROVENANCE["canonical"] is True
    assert PROVENANCE["build_status"] == "PASS"
    assert PROVENANCE["px4_ros2_interface_lib_commit"] == (
        "a5b9f3cb7cb65d2be80183bad31e9a7ce9f02684"
    )
    assert PROVENANCE["historical_px4"]["commit"] == (
        "6ea3539157ca358c70a515878b77077af7d4611d"
    )
    assert PROVENANCE["px4_msgs_commit"] == (
        "392e831c1f659429ca83902e66820d7094591410"
    )
    assert PROVENANCE["ros"]["distro"] == "jazzy"
    assert PROVENANCE["guard_exception_string_present"] is False
    assert PROVENANCE["historical_px4"]["sitl_build_status"] == "PASS"
    assert PROVENANCE["historical_px4"]["binary_sha256"] == (
        "e6b2f64e63df7e0cda2e2b8013ed73156df0029ad36aefa034be70f575ba0027"
    )


def test_historical_source_hash_and_minimal_api_adapter_are_locked() -> None:
    assert hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() == PROVENANCE[
        "adapter_source_sha256"
    ]
    assert "#ifdef UAV_SF_ISSUE162_HISTORICAL_API" in SOURCE
    assert "return {kComponentName, false, px4_ros2::ModeBase::kModeIDRtl}" in SOURCE
    assert "ModeExecutorBase(node, Settings{}, owned_mode)" in SOURCE
    assert PROVENANCE["api_adaptation"]["semantic_delta"] == "none"


def test_historical_lifecycle_contract_matches_current_harness() -> None:
    assert "completed(px4_ros2::Result::Success)" in SOURCE
    assert "scheduleMode(ownedMode().id()" in SOURCE
    assert "land([this]" in SOURCE
    assert "waitUntilDisarmed" in SOURCE
    assert PROVENANCE["shared_lifecycle_contract"]["replacement"] == (
        "registered external mode replaces internal RTL"
    )


def test_offline_preflight_is_not_a_formal_replay() -> None:
    preflight = PROVENANCE["offline_registration_preflight"]
    assert preflight["formal_attempt"] is False
    assert preflight["fmu_wait_reached"] is True
    assert preflight["registration_attempted"] is False
    assert preflight["flight_started"] is False


def test_historical_monitor_has_a_bounded_hover_window() -> None:
    assert "--post-completion-capture" in MONITOR
    assert "COMPLETE_WITHOUT_TERMINAL" in MONITOR
    assert "vehicle remained armed, airborne, and in the external mode" in MONITOR


def test_historical_runner_is_isolated_bounded_and_publicly_triggered() -> None:
    assert "external/issue162_history" in RUNNER
    assert "noble-rootfs" in RUNNER
    assert "/opt/ros/jazzy/setup.bash" in RUNNER
    assert "runs/motivation/successor/historical" in RUNNER
    assert "data/processed/motivation/successor/historical" in RUNNER
    assert 'echo "commander arm" >&3' in RUNNER
    assert 'echo "commander takeoff" >&3' in RUNNER
    assert 'echo "commander mode auto:rtl" >&3' in RUNNER
    assert "--post-completion-capture 8" in RUNNER
    assert 'PX4_INSTANCE_ETC="${PX4_INSTANCE_ROOT}/etc"' in RUNNER
    assert '[[ -f "${PX4_INSTANCE_ETC}/init.d-posix/rcS" ]]' in RUNNER
    assert RUNNER.index("PX4_INSTANCE_ETC=") < RUNNER.index("LOGGER_TOPICS_TARGET=")
    assert "--transition-target-mode 18" in RUNNER
    assert "classify_successor_historical_replay.py" in RUNNER
    assert 'PX4_BUILD="${SUCCESSOR_PX4_BUILD:-' in RUNNER
    assert '--px4-binary "${PX4_BUILD}/bin/px4"' in RUNNER
    assert '--observation-profile "${OBSERVATION_PROFILE}"' in RUNNER
    assert "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc" in RUNNER
    assert "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518" in RUNNER


def test_environment_failure_precedes_historical_violation() -> None:
    assert classify(
        infrastructure_abort=True,
        observability_insufficient=False,
        successor_status="VIOLATION",
        defect_pattern_complete=True,
    ) == "ENVIRONMENT_FAILURE"
    assert classify(
        infrastructure_abort=False,
        observability_insufficient=False,
        successor_status="VIOLATION",
        defect_pattern_complete=True,
    ) == "HISTORICAL_DEFECT_REPRODUCED"


def test_instrumentation_reduced_build_is_locked() -> None:
    reduced = json.loads(
        (
            ROOT
            / "experiments/motivation/successor/instrumentation_reduced_build_provenance.json"
        ).read_text(encoding="utf-8")
    )
    assert reduced["canonical"] is True
    assert reduced["confirmation_kind"] == "instrumentation_reduced"
    assert reduced["historical_px4"]["observation_patch"]["profile"] == "BASELINE"
    assert reduced["historical_px4"]["observation_patch"]["expected_period_us"] == 100000
    assert reduced["historical_px4"]["binary_sha256"] == (
        "42e4fd3ba83eb67a560d6ba54427fc11445da469961a0c871ef409710b2f3035"
    )


def test_historical_bridge_must_cover_external_mode_through_hover_window() -> None:
    clock = {
        "status": "VALID",
        "reference_px4_us": 20_000,
        "reference_ros_ns": 1_000_000_000,
        "rate_ratio": 1.0,
        "valid_from": 10_000,
        "valid_until": 40_000,
    }
    assert bridge_window(clock, 990_000_000, 1_020_000_000)["covered"] is True
    assert bridge_window(clock, 990_000_000, 1_030_000_001)["covered"] is False
