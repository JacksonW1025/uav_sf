#!/usr/bin/env python3
"""Build an auditable TSV matrix from accepted P2 or P3 processed results."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


COMMON_COLUMNS = [
    "run_id",
    "object",
    "experiment_verdict",
    "clock_bridge_status",
    "clock_bridge_id",
    "clock_uncertainty_ns",
    "source_route_epoch_id",
    "automatic_fallback_observed",
    "fallback_nav_state",
    "fallback_route_epoch_id",
    "post_revocation_old_epoch_consumption_count",
    "post_revocation_old_epoch_writer_count",
    "altitude_loss_m",
    "peak_tilt_rad",
    "peak_angular_rate_rad_s",
    "route_oracle_status",
    "revocation",
    "installation",
    "exclusivity",
    "continuity",
    "recovery",
    "full_trace_event_count",
    "compact_trace_event_count",
]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(phase: str, processed_root: Path) -> tuple[list[str], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    for result_path in sorted(processed_root.glob("*/experiment_result.json")):
        directory = result_path.parent
        result = _load(result_path)
        oracle = _load(directory / "route_oracle.json")
        compact = _load(directory / "trace_compaction.json")
        fallback = result["failure_and_fallback"]
        physical = result["physical_recovery"]
        clauses = result["route_oracle_clauses"]
        row: dict[str, object] = {
            "run_id": directory.name,
            "object": result["object"],
            "experiment_verdict": result["verdict"],
            "clock_bridge_status": result["clock_bridge"]["status"],
            "clock_bridge_id": result["clock_bridge"]["clock_bridge_id"],
            "clock_uncertainty_ns": result["clock_bridge"]["uncertainty_ns"],
            "source_route_epoch_id": result["source_route"]["route_epoch_id"],
            "automatic_fallback_observed": fallback["automatic_fallback_observed"],
            "fallback_nav_state": fallback["fallback_nav_state"],
            "fallback_route_epoch_id": fallback["fallback_route_epoch_id"],
            "post_revocation_old_epoch_consumption_count": fallback[
                "post_revocation_old_epoch_consumption_count"
            ],
            "post_revocation_old_epoch_writer_count": fallback[
                "post_revocation_old_epoch_writer_count"
            ],
            "altitude_loss_m": physical["altitude_loss_m"],
            "peak_tilt_rad": physical["peak_tilt_rad"],
            "peak_angular_rate_rad_s": physical["peak_angular_rate_rad_s"],
            "route_oracle_status": oracle["status"],
            "revocation": clauses["revocation"],
            "installation": clauses["installation"],
            "exclusivity": clauses["exclusivity"],
            "continuity": clauses["continuity"],
            "recovery": clauses["recovery"],
            "full_trace_event_count": compact["full_event_count"],
            "compact_trace_event_count": compact["compact_event_count"],
        }
        if phase == "p2":
            interval = result["clock_bridge"]["fault_px4_time_interval"]
            row.update(
                {
                    "fault_class": result["fault_class"],
                    "fault_px4_lower_us": interval["lower_us"],
                    "fault_px4_upper_us": interval["upper_us"],
                    "failure_detection_latency_ms": fallback["detection_latency_ms"],
                    "last_producer_heartbeat_ros_ns": result["source_route"][
                        "last_producer_heartbeat_ros_ns"
                    ],
                    "last_producer_setpoint_ros_ns": result["source_route"][
                        "last_producer_setpoint_ros_ns"
                    ],
                    "last_px4_consumption_us": result["source_route"][
                        "last_px4_consumption_us"
                    ],
                    "last_allocator_event_us": result["source_route"][
                        "last_allocator_event_us"
                    ],
                    "last_writer_event_us": result["source_route"]["last_writer_event_us"],
                    "first_fallback_consumption_us": fallback[
                        "first_fallback_consumption_us"
                    ],
                    "first_fallback_allocator_event_us": fallback[
                        "first_fallback_allocator_event_us"
                    ],
                    "first_fallback_writer_event_us": fallback[
                        "first_fallback_writer_event_us"
                    ],
                }
            )
        else:
            row.update(
                {
                    "heartbeat_or_health_enabled": result[
                        "heartbeat_or_health_enabled"
                    ],
                    "setpoint_enabled": result["setpoint_enabled"],
                    "expected_fallback": fallback["expected_fallback"],
                }
            )
        rows.append(row)

    if phase == "p2":
        group_counts = Counter((row["object"], row["fault_class"]) for row in rows)
        expected_groups = {
            (object_name, fault): 3
            for object_name in ("offboard", "external")
            for fault in ("sigterm", "sigkill", "sigstop_sigcont")
        }
        prefix = ["fault_class"]
        suffix = [
            "fault_px4_lower_us",
            "fault_px4_upper_us",
            "failure_detection_latency_ms",
            "last_producer_heartbeat_ros_ns",
            "last_producer_setpoint_ros_ns",
            "last_px4_consumption_us",
            "last_allocator_event_us",
            "last_writer_event_us",
            "first_fallback_consumption_us",
            "first_fallback_allocator_event_us",
            "first_fallback_writer_event_us",
        ]
    else:
        group_counts = Counter(
            (row["object"], row["heartbeat_or_health_enabled"], row["setpoint_enabled"])
            for row in rows
        )
        expected_groups = {
            (object_name, heartbeat_or_health, setpoint): 3
            for object_name in ("offboard", "external")
            for heartbeat_or_health in (True, False)
            for setpoint in (True, False)
        }
        prefix = ["heartbeat_or_health_enabled", "setpoint_enabled", "expected_fallback"]
        suffix = []
    if group_counts != Counter(expected_groups):
        raise ValueError(f"accepted {phase} matrix is incomplete: {dict(group_counts)}")
    if any(row["experiment_verdict"] != "PASS" for row in rows):
        raise ValueError("accepted matrix contains a non-PASS experiment verdict")
    if any(row["clock_bridge_status"] != "VALID" for row in rows):
        raise ValueError("accepted matrix contains a non-VALID clock bridge")
    return ["run_id", "object", *prefix, *COMMON_COLUMNS[2:], *suffix], rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("p2", "p3"), required=True)
    parser.add_argument("--processed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    columns, rows = build(args.phase, args.processed_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"phase": args.phase, "accepted_cases": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
