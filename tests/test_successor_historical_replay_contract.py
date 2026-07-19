import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "scripts/adapters/external_mode_adapter/src/issue162_replay.cpp"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
PROVENANCE = json.loads(
    (
        ROOT
        / "experiments/motivation/successor/historical_replay_build_provenance.json"
    ).read_text(encoding="utf-8")
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
