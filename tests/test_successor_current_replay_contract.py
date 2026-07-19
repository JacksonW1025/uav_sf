from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "scripts/adapters/external_mode_adapter/src/issue162_replay.cpp"
).read_text(encoding="utf-8")
RUNNER = (ROOT / "scripts/probes/run_successor_current_replay.sh").read_text(
    encoding="utf-8"
)
CLASSIFIER = (
    ROOT / "scripts/analysis/classify_successor_current_replay.py"
).read_text(encoding="utf-8")


def test_issue162_harness_uses_preregistered_legal_composition() -> None:
    assert ".replaceInternalMode(px4_ros2::ModeBase::kModeIDRtl)" in SOURCE
    assert "ModeExecutorBase(Settings{}, owned_mode)" in SOURCE
    assert "ActivateImmediately" not in SOURCE
    assert 'kComponentName = "Issue 162 Custom RTL"' in SOURCE
    assert "kTargetHeightM = 5.f" in SOURCE


def test_historical_api_adapter_preserves_the_same_composition() -> None:
    assert "UAV_SF_ISSUE162_HISTORICAL_API" in SOURCE
    assert "return {kComponentName, false, px4_ros2::ModeBase::kModeIDRtl}" in SOURCE
    assert "ModeExecutorBase(node, Settings{}, owned_mode)" in SOURCE


def test_issue162_completion_condition_and_successor_are_fixed() -> None:
    assert "kPositionToleranceM = 0.5f" in SOURCE
    assert "kVelocityToleranceMps = 0.5f" in SOURCE
    assert "kStableDuration = std::chrono::seconds(1)" in SOURCE
    assert "completed(px4_ros2::Result::Success)" in SOURCE
    assert "scheduleMode(ownedMode().id()" in SOURCE
    assert "land([this]" in SOURCE
    assert "waitUntilDisarmed" in SOURCE


def test_current_replay_is_bounded_exact_and_p5_isolated() -> None:
    assert "timeout 15s" in RUNNER
    assert "classify_successor_current_replay.py" in RUNNER
    assert "runs/motivation/successor/current" in RUNNER
    assert "data/processed/motivation/successor/current" in RUNNER
    assert "c3e410f035806e8c56246708432ded09c976434b" in RUNNER
    assert "9542eb7c98dfd4df1ab50026c149f21fb719fc6a2a09d040a9db4df647f132bc" in RUNNER
    assert "02d857f555623c10dc44998cd202c2da6226ec5c40a94a75020d75df87f02518" in RUNNER


def test_current_replay_records_guard_and_nonflight_disposition() -> None:
    assert '"classification": "NOT_REPRODUCED_ON_CURRENT"' in CLASSIFIER
    assert '"UNSUPPORTED_COMBINATION_REJECTED"' in CLASSIFIER
    assert '"guard_exception_match": expected_rejection' in CLASSIFIER
    assert '"registration_attempted": False' in CLASSIFIER
    assert '"flight_started": False' in CLASSIFIER
    assert "dce6c1f2e4a29e947fd32a84c4981773f1962c03" in CLASSIFIER
