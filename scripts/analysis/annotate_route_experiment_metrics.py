#!/usr/bin/env python3
"""Mark the locked DDS angular-rate metric unavailable in processed experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def annotate(root: Path) -> int:
    count = 0
    for path in sorted(root.glob("*/experiment_result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        physical = result["physical_recovery"]
        physical.update(
            {
                "attitude_measurement_status": "AVAILABLE",
                "angular_rate_measurement_status": (
                    "UNKNOWN_NOT_PUBLISHED_BY_LOCKED_DDS_CONFIG"
                ),
                "angular_rate_sample_count": 0,
                "peak_angular_rate_rad_s": None,
            }
        )
        if result["experiment_kind"] == "p2":
            source = result["source_route"]
            if result["object"] == "external":
                source["last_producer_heartbeat_ros_ns"] = None
                source[
                    "producer_heartbeat_measurement_status"
                ] = "UNKNOWN_EXTERNAL_HEALTH_REPLY_NOT_LOGGED"
            else:
                source["producer_heartbeat_measurement_status"] = "AVAILABLE"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-root", type=Path, action="append", required=True)
    args = parser.parse_args()
    count = sum(annotate(root) for root in args.processed_root)
    print(json.dumps({"annotated_results": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
