#!/usr/bin/env python3
"""P0-D0: internal-only RTL auto-disarm and rapid-rearm baseline."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probes.p0_route_runner import _versioned_topic


def run(output: Path, timeout_s: float) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            FailsafeFlags,
            TimesyncStatus,
            VehicleCommand,
            VehicleCommandAck,
            VehicleLandDetected,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    class Probe(Node):
        def __init__(self) -> None:
            super().__init__("p0d0_internal_rearm")
            output.parent.mkdir(parents=True, exist_ok=True)
            self.events = output.with_name("producer_events.jsonl").open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + timeout_s
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.last_command = 0.0
            self.status: Any = None
            self.position: Any = None
            self.land: Any = None
            self.failsafe: Any = None
            self.timesync: Any = None
            self.arm_attempt = 0
            self.command_acks: list[dict[str, int]] = []
            self.first_disarm_ns: int | None = None
            self.second_arm_ns: int | None = None
            self.exit_code: int | None = None
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            subscriptions = (
                (VehicleStatus, "/fmu/out/vehicle_status", self._status),
                (VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._position),
                (VehicleLandDetected, "/fmu/out/vehicle_land_detected", self._land),
                (FailsafeFlags, "/fmu/out/failsafe_flags", self._failsafe),
                (VehicleCommandAck, "/fmu/out/vehicle_command_ack", self._ack),
                (TimesyncStatus, "/fmu/out/timesync_status", self._timesync),
            )
            for message_type, topic, callback in subscriptions:
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, qos
                )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.timer = self.create_timer(0.05, self._tick)
            self._event("p0d0_started")

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
            previous = self.status
            self.status = message
            if previous is None or (
                int(previous.nav_state), int(previous.arming_state)
            ) != (int(message.nav_state), int(message.arming_state)):
                self._event(
                    "vehicle_status_sample",
                    nav_state=int(message.nav_state),
                    arming_state=int(message.arming_state),
                    failsafe=bool(message.failsafe),
                )

        def _position(self, message: Any) -> None:
            self.position = message

        def _land(self, message: Any) -> None:
            self.land = message

        def _failsafe(self, message: Any) -> None:
            self.failsafe = message

        def _ack(self, message: Any) -> None:
            ack = {
                "command": int(message.command),
                "result": int(message.result),
                "result_param1": int(message.result_param1),
                "result_param2": int(message.result_param2),
            }
            self.command_acks.append(ack)
            self._event("vehicle_command_ack", **ack)

        def _timesync(self, message: Any) -> None:
            self.timesync = message
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
            if command == VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM and params.get("param1") == 1:
                self.arm_attempt += 1
            self._event("vehicle_command", command=command, params=params, arm_attempt=self.arm_attempt)

        def _periodic(self, command: int, period_s: float = 1.0, **params: float) -> None:
            now = time.monotonic()
            if now - self.last_command >= period_s:
                self.last_command = now
                self._command(command, **params)

        def _armed(self) -> bool:
            return self.status is not None and int(self.status.arming_state) == int(
                VehicleStatus.ARMING_STATE_ARMED
            )

        def _failure_snapshot(self) -> dict[str, object]:
            failed_flags = []
            if self.failsafe is not None:
                for field, field_type in self.failsafe.get_fields_and_field_types().items():
                    if field_type == "boolean" and bool(getattr(self.failsafe, field)):
                        failed_flags.append(field)
            return {
                "nav_state": int(self.status.nav_state) if self.status else None,
                "landed": bool(self.land.landed) if self.land else None,
                "xy_valid": bool(self.position.xy_valid) if self.position else None,
                "z_valid": bool(self.position.z_valid) if self.position else None,
                "failed_failsafe_flags": failed_flags,
                "command_acks": self.command_acks[-10:],
            }

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "scenario": "p0d0_internal_rearm",
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "external_component_started": False,
                "first_disarm_monotonic_ns": self.first_disarm_ns,
                "second_arm_monotonic_ns": self.second_arm_ns,
                "rearm_delay_s": (
                    (self.second_arm_ns - self.first_disarm_ns) / 1e9
                    if self.first_disarm_ns is not None and self.second_arm_ns is not None
                    else None
                ),
                "failure_snapshot": self._failure_snapshot(),
            }
            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
                if self.status is not None and self.position is not None and bool(self.position.xy_valid):
                    self._transition("ARM_FIRST")
                return
            if self.state == "ARM_FIRST":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self._transition("TAKEOFF_FIRST")
                return
            if self.state == "TAKEOFF_FIRST":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if float(self.position.z) < -2.0:
                    self._transition("RTL_FIRST")
                return
            if self.state == "RTL_FIRST":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
                if not self._armed():
                    self.first_disarm_ns = time.monotonic_ns()
                    self._transition("POST_DISARM_WAIT")
                return
            if self.state == "POST_DISARM_WAIT":
                if now - self.state_started >= 5.0:
                    self._transition("SELECT_HOLD")
                return
            if self.state == "SELECT_HOLD":
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
                if int(self.status.nav_state) == int(
                    VehicleStatus.NAVIGATION_STATE_AUTO_LOITER
                ):
                    self._transition("ARM_SECOND")
                elif now - self.state_started >= 5.0:
                    self._finish("FAIL", "internal Hold mode could not be selected after auto-disarm")
                return
            if self.state == "ARM_SECOND":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self.second_arm_ns = time.monotonic_ns()
                    self._transition("TAKEOFF_SECOND")
                elif now - self.state_started >= 15.0:
                    self._finish("FAIL", "internal rearm denied after RTL auto-disarm")
                return
            if self.state == "TAKEOFF_SECOND":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if float(self.position.z) < -2.0:
                    self._transition("HOVER_SECOND")
                return
            if self.state == "HOVER_SECOND":
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
                if now - self.state_started >= 5.0:
                    self._transition("LAND_SECOND")
                return
            if self.state == "LAND_SECOND":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                if not self._armed():
                    self._finish("PASS", "internal RTL auto-disarm and rapid rearm completed")

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
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    return run(args.output, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
