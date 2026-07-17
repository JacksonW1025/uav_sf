#!/usr/bin/env python3
"""Low-risk P0-D probe for post-disarm External Mode retention and clean re-entry."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probes.p0_route_runner import _name, _versioned_topic


def run(
    output: Path,
    shutdown_request: Path,
    shutdown_done: Path,
    timeout_s: float,
    *,
    select_internal_before_rearm: bool = False,
    scenario_label: str = "p0d_post_disarm_reentry",
) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            RegisterExtComponentReply,
            TimesyncStatus,
            UnregisterExtComponent,
            VehicleCommand,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    class Probe(Node):
        def __init__(self) -> None:
            super().__init__("p0d_post_disarm_reentry")
            self.output = output
            self.events_path = output.with_name("producer_events.jsonl")
            self.events = self.events_path.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + timeout_s
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.status: Optional[Any] = None
            self.local_position: Optional[Any] = None
            self.external_mode_id: Optional[int] = None
            self.last_command = 0.0
            self.armed_once = False
            self.first_disarm_nav_state: Optional[int] = None
            self.post_disarm_nav_states: list[int] = []
            self.unregister_requests = 0
            self.rearm_initial_nav_state: Optional[int] = None
            self.automatic_external_after_rearm = False
            self.rearm_initial_attempt_blocked = False
            self.rearm_recovered_after_internal_request = False
            self.pre_rearm_nav_state: Optional[int] = None
            self.exit_code: Optional[int] = None
            self.timesync_status: Optional[Any] = None

            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            self.create_subscription(
                TimesyncStatus,
                _versioned_topic("/fmu/out/timesync_status", TimesyncStatus),
                self._timesync,
                qos,
            )
            self.create_subscription(
                VehicleStatus,
                _versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
                self._status,
                qos,
            )
            self.create_subscription(
                VehicleLocalPosition,
                _versioned_topic("/fmu/out/vehicle_local_position", VehicleLocalPosition),
                self._position,
                qos,
            )
            self.create_subscription(
                RegisterExtComponentReply,
                _versioned_topic("/fmu/out/register_ext_component_reply", RegisterExtComponentReply),
                self._registration,
                qos,
            )
            self.create_subscription(
                UnregisterExtComponent,
                "/fmu/in/unregister_ext_component",
                self._unregister,
                10,
            )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.timer = self.create_timer(0.05, self._tick)
            self._event("p0d_started")

        def _event(self, event_type: str, **fields: object) -> None:
            record = {
                "event_type": event_type,
                "monotonic_ns": time.monotonic_ns(),
                "ros_time_ns": self.get_clock().now().nanoseconds,
                "state": self.state,
                **fields,
            }
            self.events.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            self.events.flush()

        def _transition(self, state: str) -> None:
            previous = self.state
            self.state = state
            self.state_started = time.monotonic()
            self.last_command = 0.0
            self._event("state_transition", previous=previous, current=state)

        def _status(self, message: Any) -> None:
            previous_nav = int(self.status.nav_state) if self.status is not None else None
            previous_arming = int(self.status.arming_state) if self.status is not None else None
            self.status = message
            nav_state = int(message.nav_state)
            arming_state = int(message.arming_state)
            if previous_nav != nav_state or previous_arming != arming_state:
                self._event(
                    "vehicle_status_sample",
                    nav_state=nav_state,
                    arming_state=arming_state,
                )
            if arming_state == int(VehicleStatus.ARMING_STATE_ARMED):
                self.armed_once = True
                if self.state in {"REARM", "REQUEST_HOLD", "OBSERVE_REENTRY"}:
                    if self.rearm_initial_nav_state is None:
                        self.rearm_initial_nav_state = nav_state
                    if self.external_mode_id is not None and nav_state == self.external_mode_id:
                        self.automatic_external_after_rearm = True
            if self.state == "POST_DISARM":
                if not self.post_disarm_nav_states or self.post_disarm_nav_states[-1] != nav_state:
                    self.post_disarm_nav_states.append(nav_state)

        def _position(self, message: Any) -> None:
            self.local_position = message

        def _registration(self, message: Any) -> None:
            name = _name(message.name)
            if bool(message.success) and name == "Route Transition":
                self.external_mode_id = int(message.mode_id)
                self._event("external_mode_registration_observed", name=name, mode_id=self.external_mode_id)

        def _unregister(self, message: Any) -> None:
            self.unregister_requests += 1
            self._event(
                "graceful_unregister_request",
                mode_id=int(getattr(message, "mode_id", -1)),
                mode_executor_id=int(getattr(message, "mode_executor_id", -1)),
                arming_check_id=int(getattr(message, "arming_check_id", -1)),
            )

        def _timesync(self, message: Any) -> None:
            self.timesync_status = message
            offset = int(message.estimated_offset)
            self._event(
                "clock_bridge_sample",
                sample_source="timesync_status",
                px4_outbound_timestamp_us=int(message.timestamp),
                px4_boot_timestamp_us=int(message.timestamp) + offset,
                ros_receive_ns=self.get_clock().now().nanoseconds,
                monotonic_receive_ns=time.monotonic_ns(),
                timesync_source_protocol=int(message.source_protocol),
                timesync_estimated_offset_us=offset,
                timesync_round_trip_time_us=int(message.round_trip_time),
                timesync_converged=int(message.source_protocol) == 2,
            )

        def _command(self, command: int, **params: float) -> None:
            message = VehicleCommand()
            message.timestamp = self.get_clock().now().nanoseconds // 1000
            message.command = int(command)
            for index in range(1, 8):
                setattr(message, f"param{index}", float(params.get(f"param{index}", math.nan)))
            message.target_system = 1
            message.target_component = 1
            message.source_system = 1
            message.source_component = 191
            message.from_external = True
            self.command_pub.publish(message)
            self._event("vehicle_command", command=int(command), params=params)

        def _periodic(self, command: int, period_s: float = 1.0, **params: float) -> None:
            now = time.monotonic()
            if now - self.last_command >= period_s:
                self.last_command = now
                self._command(command, **params)

        def _armed(self) -> bool:
            return self.status is not None and int(self.status.arming_state) == int(
                VehicleStatus.ARMING_STATE_ARMED
            )

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "scenario": scenario_label,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "external_mode_id": self.external_mode_id,
                "disarm_nav_state": self.first_disarm_nav_state,
                "post_disarm_nav_states": self.post_disarm_nav_states,
                "unregister_request_count": self.unregister_requests,
                "mode_slot_removal_evidence": False,
                "rearm_initial_nav_state": self.rearm_initial_nav_state,
                "automatic_external_after_rearm": self.automatic_external_after_rearm,
                "rearm_initial_attempt_blocked": self.rearm_initial_attempt_blocked,
                "rearm_recovered_after_internal_request": self.rearm_recovered_after_internal_request,
                "pre_rearm_nav_state": self.pre_rearm_nav_state,
            }
            self.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._event("runner_finished", **result)
            self.events.close()
            self.exit_code = 0 if status == "PASS" else 1
            self.timer.cancel()

        def _tick(self) -> None:
            now = time.monotonic()
            if now >= self.deadline:
                self._finish("FAIL", f"timeout in {self.state}")
                return
            if self.state == "WAIT_FOR_FMU":
                position_ready = self.local_position is not None and bool(self.local_position.xy_valid)
                if self.status is not None and position_ready and self.external_mode_id is not None:
                    self._transition("ARM")
                return
            if self.state == "ARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self._transition("TAKEOFF")
                return
            if self.state == "TAKEOFF":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if self.local_position is not None and float(self.local_position.z) < -2.0:
                    self._transition("ACTIVATE_EXTERNAL")
                return
            if self.state == "ACTIVATE_EXTERNAL":
                assert self.external_mode_id is not None
                self._periodic(VehicleCommand.VEHICLE_CMD_SET_NAV_STATE, param1=float(self.external_mode_id))
                if self.status is not None and int(self.status.nav_state) == self.external_mode_id:
                    self._transition("ACTIVE_EXTERNAL")
                return
            if self.state == "ACTIVE_EXTERNAL":
                if now - self.state_started >= 9.0:
                    self._transition("RTL")
                return
            if self.state == "RTL":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
                if self.armed_once and not self._armed():
                    self.first_disarm_nav_state = int(self.status.nav_state) if self.status else None
                    if self.first_disarm_nav_state is not None:
                        self.post_disarm_nav_states.append(self.first_disarm_nav_state)
                    self._transition("POST_DISARM")
                return
            if self.state == "POST_DISARM":
                if now - self.state_started >= 5.0:
                    shutdown_request.touch()
                    self._event("graceful_shutdown_requested")
                    self._transition("WAIT_UNREGISTER")
                return
            if self.state == "WAIT_UNREGISTER":
                if shutdown_done.exists() and now - self.state_started >= 3.0:
                    self._transition(
                        "REQUEST_INTERNAL_BEFORE_RETRY"
                        if select_internal_before_rearm
                        else "REARM"
                    )
                return
            if self.state == "REARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self.rearm_initial_nav_state = int(self.status.nav_state) if self.status else None
                    if self.external_mode_id is not None and self.rearm_initial_nav_state == self.external_mode_id:
                        self.automatic_external_after_rearm = True
                    self._transition("REQUEST_HOLD")
                elif now - self.state_started >= 3.0:
                    self.rearm_initial_attempt_blocked = True
                    self.pre_rearm_nav_state = int(self.status.nav_state) if self.status else None
                    self._event(
                        "rearm_initial_attempt_blocked",
                        nav_state=self.pre_rearm_nav_state,
                    )
                    self._transition("REQUEST_INTERNAL_BEFORE_RETRY")
                return
            if self.state == "REQUEST_INTERNAL_BEFORE_RETRY":
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
                if (
                    self.status is not None
                    and int(self.status.nav_state)
                    == int(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER)
                ) or now - self.state_started >= 3.0:
                    self._transition("REARM_AFTER_INTERNAL_REQUEST")
                return
            if self.state == "REARM_AFTER_INTERNAL_REQUEST":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self.rearm_initial_nav_state = int(self.status.nav_state) if self.status else None
                    self.rearm_recovered_after_internal_request = True
                    if self.external_mode_id is not None and self.rearm_initial_nav_state == self.external_mode_id:
                        self.automatic_external_after_rearm = True
                    self._transition("REQUEST_HOLD")
                elif now - self.state_started >= 15.0:
                    self._finish(
                        "FAIL",
                        "rearm remained denied after graceful unregister and explicit internal Hold selection",
                    )
                return
            if self.state == "REQUEST_HOLD":
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
                if now - self.state_started >= 1.0:
                    self._transition("OBSERVE_REENTRY")
                return
            if self.state == "OBSERVE_REENTRY":
                if now - self.state_started >= 5.0:
                    self._transition("TAKEOFF_REENTRY")
                return
            if self.state == "TAKEOFF_REENTRY":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if self.local_position is not None and float(self.local_position.z) < -2.0:
                    self._transition("LAND_REENTRY")
                return
            if self.state == "LAND_REENTRY":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                if not self._armed():
                    self._finish("PASS", "post-disarm retention and explicit internal re-entry observed")

    rclpy.init()
    node = Probe()
    while rclpy.ok() and node.exit_code is None:
        rclpy.spin_once(node, timeout_sec=0.2)
    result = node.exit_code if node.exit_code is not None else 1
    node.destroy_node()
    rclpy.shutdown()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shutdown-request", type=Path, required=True)
    parser.add_argument("--shutdown-done", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    return run(args.output, args.shutdown_request, args.shutdown_done, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
