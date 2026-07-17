#!/usr/bin/env python3
"""Analyze explicit actuator-writer evidence, sequence continuity, and transition coverage."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


P0_CANDIDATE_WRITERS = ("control_allocator",)
P0_INSTRUMENTED_WRITERS = ("control_allocator",)


def _is_external_route(mode: object) -> bool:
    return isinstance(mode, int) and (mode == 14 or 23 <= mode <= 30)


def _maximum_gap_ms(timestamps: list[float]) -> float:
    if len(timestamps) < 2:
        return 0.0
    return max(b - a for a, b in zip(timestamps, timestamps[1:])) / 1000.0


def _transitions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    previous: Any = None
    initialized = False
    for event in events:
        if event.get("timestamp_domain") != "ulog_us" or event.get("event_type") != "vehicle_status":
            continue
        mode = event.get("declared_mode")
        if initialized and mode != previous:
            changes.append(
                {
                    "timestamp_us": float(event["timestamp"]),
                    "from_mode": previous,
                    "to_mode": mode,
                }
            )
        previous = mode
        initialized = True
    return changes


def summarize(
    path: Path,
    candidate_writers: Iterable[str] | None = None,
    instrumented_candidates: Iterable[str] | None = None,
    window_padding_ms: float = 500.0,
    minimum_rate_hz: float = 100.0,
) -> dict[str, object]:
    candidates = sorted(set(candidate_writers or P0_CANDIDATE_WRITERS))
    instrumented = sorted(set(instrumented_candidates or P0_INSTRUMENTED_WRITERS))
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    writer_events = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and event.get("event_type") == "actuator_output_published"
    ]

    observed_writers = sorted(
        {
            str(event["actuator_writer"])
            for event in writer_events
            if event.get("actuator_writer") not in (None, "unknown")
        }
    )
    allocator_writers = sorted(
        {
            str(allocator["writer"])
            for event in events
            if isinstance((allocator := event.get("allocator_input")), dict)
            and allocator.get("writer") not in (None, "unknown")
        }
    )
    uninstrumented = sorted(set(candidates) - set(instrumented))
    timestamps = sorted(float(event["timestamp"]) for event in writer_events)
    maximum_gap_ms = _maximum_gap_ms(timestamps)

    sequences: dict[str, list[tuple[int, float]]] = defaultdict(list)
    expected_periods: set[int] = set()
    profiles: set[str] = set()
    missing_sequence_evidence = False
    for event in writer_events:
        observation = event.get("observation")
        writer = str(event.get("actuator_writer") or "unknown")
        if not isinstance(observation, dict):
            missing_sequence_evidence = True
            continue
        sequences[writer].append((int(observation["sequence"]), float(event["timestamp"])))
        expected_periods.add(int(observation["expected_period_us"]))
        profiles.add(str(observation["profile"]))

    sequence_gaps: list[dict[str, object]] = []
    expected_sequence_count = 0
    recorded_sequence_count = 0
    for writer, samples in sorted(sequences.items()):
        samples.sort(key=lambda item: item[1])
        recorded_sequence_count += len(samples)
        if samples:
            expected_sequence_count += samples[-1][0] - samples[0][0] + 1
        for (previous_sequence, previous_time), (sequence, timestamp) in zip(samples, samples[1:]):
            if sequence != previous_sequence + 1:
                sequence_gaps.append(
                    {
                        "writer": writer,
                        "previous_sequence": previous_sequence,
                        "next_sequence": sequence,
                        "missing_count": max(0, sequence - previous_sequence - 1),
                        "timestamp_us": timestamp,
                        "previous_timestamp_us": previous_time,
                        "next_timestamp_us": timestamp,
                        "gap_ms": (timestamp - previous_time) / 1000.0,
                    }
                )

    coverage_ratio = (
        recorded_sequence_count / expected_sequence_count if expected_sequence_count > 0 else 0.0
    )
    actual_rate_hz = 0.0
    if len(timestamps) > 1 and timestamps[-1] > timestamps[0]:
        actual_rate_hz = (len(timestamps) - 1) * 1_000_000.0 / (timestamps[-1] - timestamps[0])

    expected_period_us = next(iter(expected_periods)) if len(expected_periods) == 1 else 0
    expected_period_ms = expected_period_us / 1000.0
    transition_profile = profiles == {"TRANSITION"}
    publication_complete = (
        transition_profile
        and expected_period_us == 0
        and not missing_sequence_evidence
        and not sequence_gaps
        and coverage_ratio == 1.0
    )
    rate_gate = actual_rate_hz >= minimum_rate_hz or publication_complete

    changes = _transitions(events)
    padding_us = window_padding_ms * 1000.0
    transition_windows: list[dict[str, object]] = []
    competing_windows: list[dict[str, object]] = []
    observation_holes: list[dict[str, object]] = []

    positive_gaps = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
    median_period_us = statistics.median(positive_gaps) if positive_gaps else 0.0
    allowed_gap_us = (
        max(20_000.0, 3.0 * median_period_us)
        if expected_period_us == 0
        else max(3.0 * expected_period_us, expected_period_us + 5_000.0)
    )

    for change in changes:
        start = float(change["timestamp_us"]) - padding_us
        end = float(change["timestamp_us"]) + padding_us
        in_window = [
            event for event in writer_events if start <= float(event["timestamp"]) <= end
        ]
        window_timestamps = sorted(float(event["timestamp"]) for event in in_window)
        writers = sorted(
            {
                str(event["actuator_writer"])
                for event in in_window
                if event.get("actuator_writer") not in (None, "unknown")
            }
        )
        max_gap = _maximum_gap_ms([start, *window_timestamps, end])
        window = {
            **change,
            "window_start": start,
            "window_end": end,
            "from_route": change["from_mode"],
            "to_route": change["to_mode"],
            "start_us": start,
            "end_us": end,
            "event_count": len(in_window),
            "observed_writers": writers,
            "maximum_gap_ms": max_gap,
            "sequence_gap_count": sum(
                float(gap["previous_timestamp_us"]) <= end
                and float(gap["next_timestamp_us"]) >= start
                for gap in sequence_gaps
            ),
            "uninstrumented_candidate_writers": uninstrumented,
        }
        if uninstrumented or not in_window:
            window["coverage_verdict"] = "INSUFFICIENT"
        elif window["sequence_gap_count"] or max_gap * 1000.0 > allowed_gap_us:
            window["coverage_verdict"] = "BOUNDED"
        else:
            window["coverage_verdict"] = "COMPLETE"
        transition_windows.append(window)
        if len(writers) > 1:
            competing_windows.append(window)
        if not in_window or max_gap * 1000.0 > allowed_gap_us:
            observation_holes.append(window)

    critical_windows = [
        window
        for window in transition_windows
        if _is_external_route(window.get("from_mode"))
        or _is_external_route(window.get("to_mode"))
    ]

    if not writer_events:
        status = "NO_EVIDENCE"
    elif uninstrumented or missing_sequence_evidence:
        status = "INSUFFICIENT_COVERAGE"
    elif competing_windows or len(observed_writers) > 1:
        status = "COMPETING_WRITERS"
    elif not critical_windows or any(
        window["coverage_verdict"] == "INSUFFICIENT" for window in critical_windows
    ) or not rate_gate:
        status = "INSUFFICIENT_COVERAGE"
    elif any(window["coverage_verdict"] == "BOUNDED" for window in critical_windows):
        status = "SEQUENCE_GAP"
    elif len(observed_writers) == 1:
        status = "EXCLUSIVE"
    else:
        status = "NO_EVIDENCE"

    if not writer_events or uninstrumented or missing_sequence_evidence:
        global_status = "INSUFFICIENT"
    elif sequence_gaps or coverage_ratio < 1.0:
        global_status = "DEGRADED"
    else:
        global_status = "COMPLETE"

    window_verdicts = [str(window["coverage_verdict"]) for window in critical_windows]
    if not window_verdicts or "INSUFFICIENT" in window_verdicts:
        critical_status = "INSUFFICIENT"
    elif "BOUNDED" in window_verdicts:
        critical_status = "BOUNDED"
    else:
        critical_status = "COMPLETE"
    critical_sequence_gap_count = sum(
        int(window["sequence_gap_count"]) for window in critical_windows
    )
    critical_maximum_gap_ms = max(
        (float(window["maximum_gap_ms"]) for window in critical_windows),
        default=0.0,
    )

    return {
        "status": status,
        "global_capture_quality": {
            "status": global_status,
            "sequence_gap_count": len(sequence_gaps),
            "missing_sequence_count": sum(int(gap["missing_count"]) for gap in sequence_gaps),
            "coverage_ratio": coverage_ratio,
            "maximum_gap_ms": maximum_gap_ms,
        },
        "critical_window_quality": {
            "status": critical_status,
            "sequence_gap_count": critical_sequence_gap_count,
            "maximum_gap_ms": critical_maximum_gap_ms,
            "detectable_resolution_ms": (
                critical_maximum_gap_ms if critical_status == "BOUNDED" else 0.0
            ),
        },
        "observed_writers": observed_writers,
        "candidate_writers": candidates,
        "uninstrumented_candidates": uninstrumented,
        "event_count": len(writer_events),
        "sequence_gaps": sequence_gaps,
        "maximum_event_gap_ms": maximum_gap_ms,
        "expected_period_ms": expected_period_ms,
        "actual_rate_hz": actual_rate_hz,
        "coverage_ratio": coverage_ratio,
        "observation_profiles": sorted(profiles),
        "transition_windows": transition_windows,
        "critical_transition_windows": critical_windows,
        "competing_windows": competing_windows,
        "observation_holes": observation_holes,
        "per_publication_complete": publication_complete,
        "rate_gate_passed": rate_gate,
        "actuator_writers": observed_writers,
        "allocator_input_writers": allocator_writers,
        "actuator_output_events": len(writer_events),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route_trace", type=Path)
    parser.add_argument("--candidate-writer", action="append")
    parser.add_argument("--instrumented-writer", action="append")
    parser.add_argument("--window-padding-ms", type=float, default=500.0)
    args = parser.parse_args()
    result = summarize(
        args.route_trace,
        candidate_writers=args.candidate_writer,
        instrumented_candidates=args.instrumented_writer,
        window_padding_ms=args.window_padding_ms,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "EXCLUSIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
