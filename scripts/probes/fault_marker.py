#!/usr/bin/env python3
"""Create and validate observation-only fault timing bounds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def make_marker(
    marker_id: str,
    *,
    fault_class: str,
    target_session: str,
    host_before_ns: int,
    host_after_ns: int,
    lower_px4_us: float | None,
    upper_px4_us: float | None,
    px4_receipt_us: float | None,
    route_epoch_id: int | None,
) -> dict[str, Any]:
    if host_after_ns < host_before_ns:
        raise ValueError("fault timing bound is reversed")
    if (lower_px4_us is None) != (upper_px4_us is None):
        raise ValueError("PX4 lower/upper bounds must be present together")
    if lower_px4_us is not None and upper_px4_us is not None and upper_px4_us < lower_px4_us:
        raise ValueError("PX4 timing bound is reversed")
    return {
        "schema_version": "1.0",
        "fault_marker_id": marker_id,
        "host_monotonic_time": {
            "lower_ns": host_before_ns,
            "upper_ns": host_after_ns,
        },
        "ros_time_ns": None,
        "px4_receipt_time_us": px4_receipt_us,
        "route_epoch_id": route_epoch_id,
        "fault_class": fault_class,
        "target_process_session": target_session,
        "fault_time_lower_px4_us": lower_px4_us,
        "fault_time_upper_px4_us": upper_px4_us,
        "fault_time_uncertainty_us": (
            upper_px4_us - lower_px4_us
            if lower_px4_us is not None and upper_px4_us is not None
            else None
        ),
        "measurement_status": "VALID" if lower_px4_us is not None else "UNKNOWN_NO_CLOCK_MAP",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    marker = make_marker(**source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
