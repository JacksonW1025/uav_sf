#!/usr/bin/env python3
"""Aggregate the controlled uORB queue benchmark into the tracked TSV contract."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


COLUMNS = (
    "run_id",
    "uorb_queue_length",
    "profile",
    "published_sequence_range",
    "expected_event_count",
    "recorded_event_count",
    "sequence_gap_count",
    "missing_sequence_count",
    "maximum_event_gap_ms",
    "critical_window_gap_count",
    "critical_window_maximum_gap_ms",
    "critical_window_coverage",
    "global_coverage_ratio",
    "global_capture_quality",
    "critical_window_quality",
    "uorb_qsize_observed",
    "uorb_lost_message_counter",
    "uorb_loss_counter_availability",
    "logger_sequence_losses",
    "logger_write_dropouts",
    "cpu_load_mean",
    "cpu_load_max",
    "ulog_size_bytes",
    "execution_status",
    "px4_commit",
)


def _diagnostics(path: Path) -> tuple[str, int]:
    if not path.exists():
        return "", 0
    text = path.read_text(encoding="utf-8", errors="replace")
    queue_matches = re.findall(r"route_observability\s+\d+\s+\d+(?:\s+\d+)?\s+(\d+)\s+\d+", text)
    dropouts = [int(value) for value in re.findall(r"(?:dropouts:\s*|\b)(\d+)\s+dropouts", text)]
    return (queue_matches[-1] if queue_matches else "", max(dropouts, default=0))


def row(measurement_path: Path, locked_commit: str) -> dict[str, Any]:
    measurement = json.loads(measurement_path.read_text(encoding="utf-8"))
    run_id = str(measurement["run_id"])
    summary_path = measurement_path.with_name("route_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    writer = summary["writer_attribution"]
    final_groups = [group for group in measurement["groups"] if group["event_type"] == 3]
    expected = sum(group["expected_event_count"] for group in final_groups)
    actual = sum(group["actual_event_count"] for group in final_groups)
    first_sequences = [group["first_sequence"] for group in final_groups if group["first_sequence"] is not None]
    last_sequences = [group["last_sequence"] for group in final_groups if group["last_sequence"] is not None]
    sequence_range = (
        f"{min(first_sequences)}-{max(last_sequences)}"
        if first_sequences and last_sequences
        else ""
    )
    repeat_dir = measurement_path.parents[2]
    px4_log = repeat_dir / "raw" / run_id / "raw" / "px4.log"
    observed_qsize, logger_status_dropouts = _diagnostics(px4_log)
    global_quality = writer["global_capture_quality"]
    critical_quality = writer["critical_window_quality"]
    return {
        "run_id": run_id,
        "uorb_queue_length": measurement["uorb_queue_length"],
        "profile": ",".join(measurement["observation_profiles"]),
        "published_sequence_range": sequence_range,
        "expected_event_count": expected,
        "recorded_event_count": actual,
        "sequence_gap_count": global_quality["sequence_gap_count"],
        "missing_sequence_count": global_quality["missing_sequence_count"],
        "maximum_event_gap_ms": global_quality["maximum_gap_ms"],
        "critical_window_gap_count": critical_quality["sequence_gap_count"],
        "critical_window_maximum_gap_ms": critical_quality["maximum_gap_ms"],
        "critical_window_coverage": 1.0 if critical_quality["status"] == "COMPLETE" else "",
        "global_coverage_ratio": global_quality["coverage_ratio"],
        "global_capture_quality": global_quality["status"],
        "critical_window_quality": critical_quality["status"],
        "uorb_qsize_observed": observed_qsize or measurement["uorb_queue_length"],
        "uorb_lost_message_counter": "",
        "uorb_loss_counter_availability": "not_exposed_by_locked_uorb_status;publisher_sequence_used",
        "logger_sequence_losses": global_quality["missing_sequence_count"],
        "logger_write_dropouts": max(
            int(measurement.get("logger_write_dropout_count", 0)), logger_status_dropouts
        ),
        "cpu_load_mean": measurement["cpu_load_mean"],
        "cpu_load_max": measurement["cpu_load_max"],
        "ulog_size_bytes": measurement["ulog_size_bytes"],
        "execution_status": summary["execution_status"],
        "px4_commit": locked_commit,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--px4-commit", required=True)
    args = parser.parse_args()
    rows = [
        row(path, args.px4_commit)
        for path in sorted(args.run_root.rglob("observation_measurement.json"))
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": "PASS", "rows": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
