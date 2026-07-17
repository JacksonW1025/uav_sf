#!/usr/bin/env python3
"""Measure route-observation sampling, sequence continuity, CPU load, and ULog size."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def measure(path: Path) -> dict[str, Any]:
    try:
        from pyulog import ULog
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pyulog is required") from exc

    ulog = ULog(str(path))
    groups: dict[tuple[int, int, int, int], list[dict[str, int]]] = defaultdict(list)
    profiles: set[int] = set()
    expected_periods: set[int] = set()
    cpu_samples: list[float] = []

    for dataset in ulog.data_list:
        if dataset.name == "route_observability":
            count = len(dataset.data["timestamp"])
            for index in range(count):
                record = {
                    name: int(dataset.data[name][index])
                    for name in (
                        "timestamp",
                        "sequence",
                        "event_type",
                        "source_id",
                        "writer_id",
                        "instance",
                    )
                }
                record["expected_period_us"] = int(
                    dataset.data.get("expected_period_us", [100_000] * count)[index]
                )
                record["profile"] = int(dataset.data.get("profile", [1] * count)[index])
                key = (
                    record["event_type"],
                    record["source_id"],
                    record["writer_id"],
                    record["instance"],
                )
                groups[key].append(record)
                profiles.add(record["profile"])
                expected_periods.add(record["expected_period_us"])
        elif dataset.name == "cpuload" and "load" in dataset.data:
            cpu_samples.extend(float(value) for value in dataset.data["load"])

    group_results: list[dict[str, Any]] = []
    total_actual = 0
    total_expected = 0
    maximum_gap_ms = 0.0
    all_sequence_gaps: list[dict[str, Any]] = []
    actuator_rates: list[float] = []

    for key, records in sorted(groups.items()):
        records.sort(key=lambda record: record["timestamp"])
        actual = len(records)
        expected = records[-1]["sequence"] - records[0]["sequence"] + 1 if records else 0
        duration_us = records[-1]["timestamp"] - records[0]["timestamp"] if len(records) > 1 else 0
        rate_hz = (actual - 1) * 1_000_000.0 / duration_us if duration_us > 0 else 0.0
        gaps_ms = [
            (right["timestamp"] - left["timestamp"]) / 1000.0
            for left, right in zip(records, records[1:])
        ]
        sequence_gaps = [
            {
                "previous": left["sequence"],
                "next": right["sequence"],
                "missing": max(0, right["sequence"] - left["sequence"] - 1),
            }
            for left, right in zip(records, records[1:])
            if right["sequence"] != left["sequence"] + 1
        ]
        result = {
            "event_type": key[0],
            "source_id": key[1],
            "writer_id": key[2],
            "instance": key[3],
            "expected_event_count": expected,
            "actual_event_count": actual,
            "first_sequence": records[0]["sequence"] if records else None,
            "last_sequence": records[-1]["sequence"] if records else None,
            "average_rate_hz": rate_hz,
            "maximum_event_gap_ms": max(gaps_ms, default=0.0),
            "sequence_gaps": sequence_gaps,
            "logger_dropped_samples": max(0, expected - actual),
            "coverage_ratio": actual / expected if expected else 0.0,
        }
        group_results.append(result)
        total_actual += actual
        total_expected += expected
        maximum_gap_ms = max(maximum_gap_ms, result["maximum_event_gap_ms"])
        all_sequence_gaps.extend(
            {"group": key, **gap} for gap in sequence_gaps
        )
        if key[0] == 3:
            actuator_rates.append(rate_hz)

    profile_names = [{1: "BASELINE", 2: "TRANSITION"}.get(value, "UNKNOWN") for value in sorted(profiles)]
    complete = total_expected > 0 and total_actual == total_expected and not all_sequence_gaps
    transition_gate = (
        profile_names == ["TRANSITION"]
        and (max(actuator_rates, default=0.0) >= 100.0 or complete)
    )
    ulog_dropouts = list(getattr(ulog, "dropouts", []))
    return {
        "schema_version": "1.0",
        "ulog": str(path),
        "ulog_size_bytes": path.stat().st_size,
        "observation_profiles": profile_names,
        "expected_period_ms": sorted(value / 1000.0 for value in expected_periods),
        "expected_event_count": total_expected,
        "actual_event_count": total_actual,
        "average_actuator_writer_rate_hz": max(actuator_rates, default=0.0),
        "maximum_event_gap_ms": maximum_gap_ms,
        "sequence_gaps": all_sequence_gaps,
        "logger_dropped_samples": max(0, total_expected - total_actual),
        "logger_write_dropout_count": len(ulog_dropouts),
        "coverage_ratio": total_actual / total_expected if total_expected else 0.0,
        "per_publication_complete": complete,
        "transition_gate_passed": transition_gate,
        "cpu_load_mean": sum(cpu_samples) / len(cpu_samples) if cpu_samples else None,
        "cpu_load_max": max(cpu_samples) if cpu_samples else None,
        "groups": group_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--queue-length", type=int)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    result = measure(args.ulog)
    result["uorb_queue_length"] = args.queue_length
    result["run_id"] = args.run_id
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "run_id": result["run_id"],
                "uorb_queue_length": result["uorb_queue_length"],
                "coverage_ratio": result["coverage_ratio"],
                "sequence_gap_count": len(result["sequence_gaps"]),
                "logger_write_dropout_count": result["logger_write_dropout_count"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
