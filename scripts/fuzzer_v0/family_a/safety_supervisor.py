#!/usr/bin/env python3
"""Continuous, process-group-scoped Family A runtime safety supervisor."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[3]
SAFETY_RULES = ROOT / "experiments/fuzzer_v0/family_a/safety_rules.yaml"


class SupervisorError(RuntimeError):
    """Supervisor setup or event input is invalid."""


@dataclass
class SupervisorState:
    started_monotonic: float
    last_heartbeat: float
    last_clock: float
    collector_heartbeats: dict[str, float] = field(default_factory=dict)
    route_epoch_seen: bool = False
    writer_lineage_seen: bool = False
    controller_lineage_seen: bool = False
    land_seen: bool = False
    disarm_seen: bool = False
    scenario_started: bool = False
    scenario_completed: bool = False
    stop_reason: str | None = None
    stop_monotonic: float | None = None
    event_count: int = 0


def _finite_values(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value
        )
    )


class SafetySupervisor:
    """Pure event evaluator used by the live process and mock-process tests."""

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
        heartbeat_timeout_s: float = 2.0,
        clock_timeout_s: float = 2.0,
        collector_timeout_s: float = 3.0,
        scenario_timeout_s: float = 150.0,
        required_collectors: tuple[str, ...] = (
            "route",
            "writer_controller",
            "clock",
        ),
    ) -> None:
        rules = yaml.safe_load(SAFETY_RULES.read_text(encoding="utf-8"))
        self.bounds = rules["physical_boundaries"]
        self.now = now
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self.clock_timeout_s = clock_timeout_s
        self.collector_timeout_s = collector_timeout_s
        self.scenario_timeout_s = scenario_timeout_s
        self.required_collectors = required_collectors
        started = now()
        self.state = SupervisorState(
            started_monotonic=started,
            last_heartbeat=started,
            last_clock=started,
            collector_heartbeats={name: started for name in required_collectors},
        )

    def ready_record(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "status": "SUPERVISOR_READY",
            "ready_monotonic": self.state.started_monotonic,
            "required_collectors": list(self.required_collectors),
            "scenario_started": False,
            "runtime_started": False,
        }

    def _stop(self, reason: str) -> None:
        if self.state.stop_reason is None:
            self.state.stop_reason = reason
            self.state.stop_monotonic = self.now()

    def observe(self, event: dict[str, Any]) -> None:
        if self.state.stop_reason is not None:
            return
        now = self.now()
        event_type = event.get("event_type")
        self.state.event_count += 1
        if event_type == "monitor_heartbeat":
            self.state.last_heartbeat = now
        elif event_type == "scenario_started":
            self.state.scenario_started = True
            self.state.started_monotonic = now
            self.state.last_heartbeat = now
            self.state.last_clock = now
            self.state.collector_heartbeats = {
                name: now for name in self.required_collectors
            }
        elif event_type == "clock_observation":
            self.state.last_clock = now
            if event.get("stalled") is True:
                self._stop("clock_stall")
        elif event_type == "collector_heartbeat":
            collector = str(event.get("collector", ""))
            if collector not in self.state.collector_heartbeats:
                self._stop("unknown_collector")
            else:
                self.state.collector_heartbeats[collector] = now
        elif event_type == "collector_failure":
            self._stop(f"collector_failure:{event.get('collector', 'unknown')}")
        elif event_type == "px4_abort":
            self._stop("PX4_abort")
        elif event_type == "observation":
            for field in (
                "command_values",
                "controller_values",
                "actuator_values",
            ):
                if field in event and not _finite_values(event[field]):
                    self._stop(f"non_finite_{field}")
                    return
            checks = (
                (
                    float(event.get("altitude_loss_m", 0.0))
                    > float(
                        self.bounds["maximum_altitude_loss_from_stable_baseline_m"]
                    ),
                    "height_boundary_exceeded",
                ),
                (
                    float(event.get("horizontal_speed_m_s", 0.0))
                    > float(self.bounds["maximum_observed_horizontal_speed_m_s"]),
                    "horizontal_speed_boundary_exceeded",
                ),
                (
                    abs(float(event.get("vertical_speed_m_s", 0.0)))
                    > float(self.bounds["maximum_observed_vertical_speed_abs_m_s"]),
                    "vertical_speed_boundary_exceeded",
                ),
                (
                    abs(float(event.get("attitude_excursion_deg", 0.0)))
                    > float(self.bounds["maximum_attitude_excursion_deg"]),
                    "attitude_boundary_exceeded",
                ),
                (
                    abs(float(event.get("body_rate_rad_s", 0.0)))
                    > float(self.bounds["maximum_body_rate_rad_s"]),
                    "body_rate_boundary_exceeded",
                ),
                (
                    event.get("unexpected_ground_contact") is True,
                    "unexpected_ground_contact",
                ),
            )
            for failed, reason in checks:
                if failed:
                    self._stop(reason)
                    return
            self.state.route_epoch_seen |= event.get("route_epoch_present") is True
            self.state.writer_lineage_seen |= event.get("writer_lineage_present") is True
            self.state.controller_lineage_seen |= (
                event.get("controller_lineage_present") is True
            )
        elif event_type == "terminal_state":
            self.state.land_seen |= event.get("landed") is True
            self.state.disarm_seen |= event.get("disarmed") is True
        elif event_type == "scenario_completed":
            self.state.scenario_completed = True
            if not self.state.route_epoch_seen:
                self._stop("missing_route_epoch")
            elif not self.state.writer_lineage_seen:
                self._stop("missing_writer_lineage")
            elif not self.state.controller_lineage_seen:
                self._stop("missing_controller_lineage")
            elif not self.state.land_seen:
                self._stop("terminal_Land_missing")
            elif not self.state.disarm_seen:
                self._stop("terminal_Disarm_missing")
        elif event_type == "scenario_timeout":
            self._stop("runner_timeout")
        else:
            self._stop("invalid_supervisor_event")

    def check_time(self) -> None:
        if (
            self.state.stop_reason is not None
            or self.state.scenario_completed
            or not self.state.scenario_started
        ):
            return
        now = self.now()
        if now - self.state.started_monotonic > self.scenario_timeout_s:
            self._stop("runner_timeout")
        elif now - self.state.last_heartbeat > self.heartbeat_timeout_s:
            self._stop("monitor_stall")
        elif now - self.state.last_clock > self.clock_timeout_s:
            self._stop("clock_stall")
        else:
            for collector, heartbeat in self.state.collector_heartbeats.items():
                if now - heartbeat > self.collector_timeout_s:
                    self._stop(f"collector_failure:{collector}")
                    break

    def result(self) -> dict[str, Any]:
        status = (
            "FORMAL_SAFETY_STOP"
            if self.state.stop_reason is not None
            else "SCENARIO_COMPLETED"
            if self.state.scenario_completed
            else "SUPERVISING"
        )
        return {
            "schema_version": "1.0",
            "status": status,
            "stop_reason": self.state.stop_reason,
            "stop_monotonic": self.state.stop_monotonic,
            "event_count": self.state.event_count,
            "route_epoch_seen": self.state.route_epoch_seen,
            "writer_lineage_seen": self.state.writer_lineage_seen,
            "controller_lineage_seen": self.state.controller_lineage_seen,
            "land_seen": self.state.land_seen,
            "disarm_seen": self.state.disarm_seen,
        }


def terminate_attempt_process_group(process_group: int) -> bool:
    """Terminate exactly one externally-created attempt process group."""
    if process_group <= 1:
        raise SupervisorError("attempt process group must be greater than 1")
    if process_group == os.getpgrp():
        raise SupervisorError("supervisor must not terminate its own process group")
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return False
    return True


def supervise_file(
    *,
    events_path: Path,
    ready_path: Path,
    output_path: Path,
    process_group: int | None,
    process_group_path: Path | None = None,
    poll_interval_s: float = 0.05,
    supervisor: SafetySupervisor | None = None,
) -> dict[str, Any]:
    instance = supervisor or SafetySupervisor()
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.write_text(
        json.dumps(instance.ready_record(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    offset = 0
    while True:
        if events_path.exists():
            with events_path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                for line in handle:
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise SupervisorError("supervisor event must be an object")
                        instance.observe(value)
                offset = handle.tell()
        instance.check_time()
        result = instance.result()
        if result["status"] in {"FORMAL_SAFETY_STOP", "SCENARIO_COMPLETED"}:
            selected_process_group = process_group
            if (
                selected_process_group is None
                and process_group_path is not None
                and process_group_path.is_file()
            ):
                selected_process_group = int(
                    process_group_path.read_text(encoding="utf-8").strip()
                )
            if (
                result["status"] == "FORMAL_SAFETY_STOP"
                and selected_process_group is not None
            ):
                result["attempt_process_group_terminated"] = (
                    terminate_attempt_process_group(selected_process_group)
                    if selected_process_group is not None
                    else False
                )
            else:
                result["attempt_process_group_terminated"] = False
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return result
        time.sleep(poll_interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt-process-group", type=int)
    parser.add_argument("--attempt-process-group-file", type=Path)
    parser.add_argument(
        "--required-collector",
        action="append",
        default=["route", "writer_controller", "clock"],
    )
    args = parser.parse_args()
    try:
        result = supervise_file(
            events_path=args.events,
            ready_path=args.ready,
            output_path=args.output,
            process_group=args.attempt_process_group,
            process_group_path=args.attempt_process_group_file,
            supervisor=SafetySupervisor(
                required_collectors=tuple(dict.fromkeys(args.required_collector))
            ),
        )
    except (SupervisorError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "SUPERVISOR_FAILURE", "reason": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "SCENARIO_COMPLETED" else 10


if __name__ == "__main__":
    sys.exit(main())
