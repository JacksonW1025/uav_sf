from __future__ import annotations

from jsonschema import Draft202012Validator

from scripts.tracing.clock_bridge_collector import SCHEMA, collect


def _sample(index: int, jitter_ns: int = 0) -> dict[str, int | str]:
    px4_us = 1_000_000 + index * 100_000
    return {
        "event_type": "clock_bridge_sample",
        "px4_boot_timestamp_us": px4_us,
        "ros_receive_ns": int(px4_us * 1000 * 1.02) + 50_000_000_000 + jitter_ns,
        "monotonic_receive_ns": 2_000_000_000 + index * 100_000_000,
        "timesync_source_protocol": 2,
        "timesync_estimated_offset_us": 50_000_000,
        "timesync_round_trip_time_us": 1000,
        "timesync_converged": True,
    }


def test_stable_bridge_is_valid() -> None:
    samples = [_sample(index, (index % 3 - 1) * 100_000) for index in range(25)]
    result = collect(samples)
    Draft202012Validator(SCHEMA).validate(result)
    assert result["status"] == "VALID"
    assert result["sample_count"] == 25
    assert result["uncertainty_ns"] >= result["residual_max_ns"]


def test_insufficient_samples_are_invalid() -> None:
    result = collect([_sample(index) for index in range(4)])
    assert result["status"] == "INVALID"
    assert "sample_count_below_preregistered_minimum" in result["reasons"]


def test_px4_restart_starts_new_segment() -> None:
    samples = [_sample(index) for index in range(25)]
    restarted = [_sample(index) for index in range(25)]
    for index, sample in enumerate(restarted):
        sample["monotonic_receive_ns"] = 5_000_000_000 + index * 100_000_000
    result = collect([*samples, *restarted])
    assert result["segment_count"] == 2
    assert result["reset_count"] == 1


def test_large_residual_is_degraded_or_invalid() -> None:
    samples = [_sample(index, 10_000_000 if index % 2 else -10_000_000) for index in range(25)]
    result = collect(
        samples,
        {
            "minimum_sample_count": 20,
            "residual_max_ns": 5_000_000,
            "degraded_residual_max_ns": 20_000_000,
            "maximum_round_trip_time_ns": 20_000_000,
            "maximum_timesync_offset_span_ns": 5_000_000,
            "segment_jump_ns": 50_000_000,
        },
    )
    assert result["status"] == "DEGRADED"


def test_initial_dds_delivery_backlog_is_explicitly_discarded() -> None:
    samples = [_sample(index) for index in range(25)]
    samples[0]["ros_receive_ns"] = int(samples[1]["ros_receive_ns"]) - 1_000_000
    result = collect(samples)
    assert result["status"] == "VALID"
    assert result["discarded_initial_backlog_samples"] == 2
    assert result["sample_count"] == 23
