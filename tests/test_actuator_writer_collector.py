from __future__ import annotations

import json
from pathlib import Path

from scripts.tracing.actuator_writer_collector import summarize


def _status(timestamp: int, mode: int) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "timestamp_domain": "ulog_us",
        "event_type": "vehicle_status",
        "declared_mode": mode,
    }


def _writer(timestamp: int, sequence: int, writer: str = "control_allocator", writer_id: int = 2) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "timestamp_domain": "ulog_us",
        "event_type": "actuator_output_published",
        "actuator_writer": writer,
        "allocator_input": None,
        "observation": {
            "sequence": sequence,
            "event_id": 3,
            "source_id": writer_id + 1,
            "topic_id": 3,
            "writer_id": writer_id,
            "instance": 0,
            "profile": "TRANSITION",
            "expected_period_us": 0,
            "subject_timestamp": timestamp,
        },
    }


def _write(path: Path, events: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return path


def _complete_events() -> list[dict[str, object]]:
    events = [_status(0, 4), _status(100_000, 14)]
    events.extend(_writer(timestamp, index) for index, timestamp in enumerate(range(0, 210_000, 10_000)))
    return events


def test_single_writer_complete_continuous(tmp_path: Path) -> None:
    result = summarize(_write(tmp_path / "trace.jsonl", _complete_events()), window_padding_ms=50)
    assert result["status"] == "EXCLUSIVE"
    assert result["coverage_ratio"] == 1.0
    assert result["actual_rate_hz"] >= 100
    assert result["sequence_gaps"] == []
    assert result["global_capture_quality"]["status"] == "COMPLETE"
    assert result["critical_window_quality"]["status"] == "COMPLETE"


def test_two_writers_overlap(tmp_path: Path) -> None:
    events = _complete_events()
    events.extend(
        _writer(timestamp, index, "rover_ackermann", 3)
        for index, timestamp in enumerate(range(60_000, 150_000, 10_000))
    )
    result = summarize(
        _write(tmp_path / "trace.jsonl", events),
        candidate_writers=["control_allocator", "rover_ackermann"],
        instrumented_candidates=["control_allocator", "rover_ackermann"],
        window_padding_ms=50,
    )
    assert result["status"] == "COMPETING_WRITERS"
    assert result["competing_windows"]


def test_sequence_gap(tmp_path: Path) -> None:
    events = _complete_events()
    writer_events = [event for event in events if event["event_type"] == "actuator_output_published"]
    writer_events[10]["observation"]["sequence"] = 11  # type: ignore[index]
    result = summarize(_write(tmp_path / "trace.jsonl", events), window_padding_ms=50)
    assert result["status"] == "SEQUENCE_GAP"
    assert result["sequence_gaps"]
    assert result["global_capture_quality"]["status"] == "DEGRADED"


def test_missing_candidate_instrumentation(tmp_path: Path) -> None:
    result = summarize(
        _write(tmp_path / "trace.jsonl", _complete_events()),
        candidate_writers=["control_allocator", "mc_raptor"],
        instrumented_candidates=["control_allocator"],
        window_padding_ms=50,
    )
    assert result["status"] == "INSUFFICIENT_COVERAGE"
    assert result["uninstrumented_candidates"] == ["mc_raptor"]


def test_observation_window_hole(tmp_path: Path) -> None:
    events = [_status(0, 4), _status(100_000, 14)]
    events.extend(_writer(timestamp, index) for index, timestamp in enumerate((0, 10_000, 190_000, 200_000)))
    result = summarize(_write(tmp_path / "trace.jsonl", events), window_padding_ms=50)
    assert result["status"] == "INSUFFICIENT_COVERAGE"
    assert result["observation_holes"]


def test_no_events(tmp_path: Path) -> None:
    result = summarize(_write(tmp_path / "trace.jsonl", [_status(0, 4), _status(100_000, 14)]))
    assert result["status"] == "NO_EVIDENCE"
    assert result["event_count"] == 0
