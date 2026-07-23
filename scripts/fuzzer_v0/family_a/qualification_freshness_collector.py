#!/usr/bin/env python3
"""Derive a conservative Freshness Oracle input from qualification artifacts.

The P2/P3 qualification scenarios predate the dedicated freshness harness.  This
collector maps only facts present in their route-monitor artifacts and leaves
all unavailable timing windows explicitly incomplete.  It therefore enables
the required Oracle invocation without manufacturing a PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


class FreshnessCollectionError(RuntimeError):
    """Qualification artifacts cannot support even a conservative observation."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FreshnessCollectionError(f"{path}: expected an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ):
        return float(value)
    return None


def collect(
    *,
    run_id: str,
    fault_type: str,
    monitor_result: Path,
    monitor_events: Path,
    route_trace: Path,
    clock_bridge: Path,
    output: Path,
    fault_record: Path | None = None,
) -> dict[str, Any]:
    required = (monitor_result, monitor_events, route_trace, clock_bridge)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FreshnessCollectionError(f"required qualification artifacts missing: {missing}")
    monitor = _load_json(monitor_result)
    clock = _load_json(clock_bridge)
    fault = _load_json(fault_record) if fault_record and fault_record.is_file() else {}
    physical = monitor.get("physical_recovery")
    if not isinstance(physical, dict):
        physical = {}
    producer_stopped = (
        bool(fault)
        if fault_type == "TOTAL_PROCESS_STOP"
        else monitor.get("setpoint_enabled") is False
    )
    environment_status = (
        "VALID"
        if monitor.get("status") == "PASS" and clock.get("status") == "VALID"
        else "ENVIRONMENT_FAILURE"
    )
    observation: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "setpoint_type": "TRAJECTORY",
        "fault_type": fault_type,
        "producer_stopped": producer_stopped,
        "health_alive_through_target_window": (
            monitor.get("heartbeat_or_health_enabled") is True
            if fault_type == "SETPOINT_ONLY_STALL"
            else False
        ),
        "external_route_retained_at_window_end": False,
        "environment_status": environment_status,
        "clock_bridge_status": clock.get("status", "UNKNOWN"),
        "windows": {
            "pre_fault_stable": "INCOMPLETE",
            "pre_revocation_target": "INCOMPLETE",
            "fallback": "INCOMPLETE",
        },
        "timestamps_us": {
            "fault_injection": None,
            "producer_last_publish": None,
            "px4_last_setpoint_receive": None,
            "last_fresh_setpoint": None,
            "last_setpoint_consumption": None,
            "last_external_allocator_input": None,
            "last_external_writer_output": None,
            "health_loss_detection": None,
            "fallback_declared": None,
            "fallback_installed": None,
            "physical_recovery": None,
            "target_window_end": None,
        },
        "physical_metrics": {
            "maximum_attitude_excursion_deg": (
                math.degrees(float(physical["peak_tilt_rad"]))
                if _finite(physical.get("peak_tilt_rad")) is not None
                else None
            ),
            "maximum_angular_rate_excursion_rad_s": _finite(
                physical.get("peak_angular_rate_rad_s")
            ),
            "altitude_loss_m": _finite(physical.get("altitude_loss_m")),
            "horizontal_displacement_m": None,
        },
        "evidence_quality": {
            "qualification_mapping": "CONSERVATIVE_INCOMPLETE_WINDOWS",
            "required_trace_complete": False,
            "no_default_pass": True,
        },
        "inputs": [
            {"path": str(path), "sha256": _sha256(path)}
            for path in required
        ]
        + (
            [{"path": str(fault_record), "sha256": _sha256(fault_record)}]
            if fault_record and fault_record.is_file()
            else []
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(observation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--fault-type",
        choices=("TOTAL_PROCESS_STOP", "SETPOINT_ONLY_STALL"),
        required=True,
    )
    parser.add_argument("--monitor-result", type=Path, required=True)
    parser.add_argument("--monitor-events", type=Path, required=True)
    parser.add_argument("--route-trace", type=Path, required=True)
    parser.add_argument("--clock-bridge", type=Path, required=True)
    parser.add_argument("--fault-record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = collect(
            run_id=args.run_id,
            fault_type=args.fault_type,
            monitor_result=args.monitor_result,
            monitor_events=args.monitor_events,
            route_trace=args.route_trace,
            clock_bridge=args.clock_bridge,
            output=args.output,
            fault_record=args.fault_record,
        )
    except (FreshnessCollectionError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "environment_status": value["environment_status"],
                "windows": value["windows"],
                "runtime_started": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
