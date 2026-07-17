#!/usr/bin/env python3
"""Run the low-risk P0 Offboard or registered External Mode control plane."""

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

from scripts.adapters.offboard_adapter import Px4OffboardAdapter
from scripts.behavior.common_behavior_core import CommonBehaviorCore


def _name(value: object) -> str:
    if isinstance(value, str):
        return value.rstrip("\x00")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).split(b"\0", 1)[0].decode("utf-8", errors="replace")
    try:
        return bytes(int(item) for item in value).split(b"\0", 1)[0].decode("utf-8", errors="replace")
    except (TypeError, ValueError):
        return str(value)


def _versioned_topic(base: str, message_type: object) -> str:
    """Match px4_ros2_interface_lib's non-Zenoh message-version suffix."""
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def run(
    scenario: str,
    output: Path,
    timeout_s: float,
    active_duration_s: float | None = None,
    hover_only: bool = False,
    post_disarm_capture_s: float = 0.0,
) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            RegisterExtComponentReply,
            TimesyncStatus,
            VehicleCommand,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover - requires the ROS environment
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    class Runner(Node):
        def __init__(self) -> None:
            super().__init__(f"p0_{scenario}_runner")
            self.scenario = scenario
            self.output = output
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.events_path = output.with_name("producer_events.jsonl")
            self.events = self.events_path.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + timeout_s
            self.state_started = self.started
            self.last_command = 0.0
            self.state = "WAIT_FOR_FMU"
            self.status: Optional[Any] = None
            self.local_position: Optional[Any] = None
            self.external_mode_id: Optional[int] = None
            self.armed_seen = False
            self.exit_code: Optional[int] = None
            self.core = CommonBehaviorCore()
            self.active_started = 0.0
            self.active_duration_s = active_duration_s
            self.hover_only = hover_only
            self.post_disarm_capture_s = post_disarm_capture_s
            self.timesync_status: Optional[Any] = None

            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=5,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            self.create_subscription(
                VehicleStatus,
                _versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
                self._status,
                qos,
            )
            self.create_subscription(
                TimesyncStatus,
                _versioned_topic("/fmu/out/timesync_status", TimesyncStatus),
                self._timesync,
                qos,
            )
            self.create_subscription(
                VehicleLocalPosition,
                _versioned_topic("/fmu/out/vehicle_local_position", VehicleLocalPosition),
                self._local_position,
                qos,
            )
            self.create_subscription(
                RegisterExtComponentReply,
                _versioned_topic(
                    "/fmu/out/register_ext_component_reply", RegisterExtComponentReply
                ),
                self._registration,
                qos,
            )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.offboard = (
                Px4OffboardAdapter(
                    self, event_sink=lambda event: self._event("adapter_event", adapter_event=event)
                )
                if scenario == "offboard"
                else None
            )
            self.timer = self.create_timer(0.05, self._tick)
            self._event("runner_started", scenario=scenario)

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
            self.status = message
            if int(message.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED):
                self.armed_seen = True

        def _local_position(self, message: Any) -> None:
            self.local_position = message

        def _registration(self, message: Any) -> None:
            name = _name(message.name)
            if bool(message.success) and name == "Route Transition" and int(message.mode_id) >= 0:
                self.external_mode_id = int(message.mode_id)
                self._event("external_mode_registration_observed", name=name, mode_id=self.external_mode_id)

        def _timesync(self, message: Any) -> None:
            self.timesync_status = message
            self._clock_sample(int(message.timestamp), sample_source="timesync_status")

        def _clock_sample(self, outbound_timestamp_us: int, *, sample_source: str) -> None:
            assert self.timesync_status is not None
            receive_ros_ns = self.get_clock().now().nanoseconds
            receive_monotonic_ns = time.monotonic_ns()
            estimated_offset_us = int(self.timesync_status.estimated_offset)
            self._event(
                "clock_bridge_sample",
                sample_source=sample_source,
                px4_outbound_timestamp_us=outbound_timestamp_us,
                px4_boot_timestamp_us=outbound_timestamp_us + estimated_offset_us,
                ros_receive_ns=receive_ros_ns,
                monotonic_receive_ns=receive_monotonic_ns,
                timesync_source_protocol=int(self.timesync_status.source_protocol),
                timesync_estimated_offset_us=estimated_offset_us,
                timesync_round_trip_time_us=int(self.timesync_status.round_trip_time),
                timesync_converged=int(self.timesync_status.source_protocol) == 2,
            )

        def _timestamp_us(self) -> int:
            return self.get_clock().now().nanoseconds // 1000

        def _command(self, command: int, **params: float) -> None:
            message = VehicleCommand()
            message.timestamp = self._timestamp_us()
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

        def _command_periodic(self, command: int, period_s: float = 1.0, **params: float) -> None:
            now = time.monotonic()
            if now - self.last_command >= period_s:
                self.last_command = now
                self._command(command, **params)

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "scenario": self.scenario,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "armed_seen": self.armed_seen,
                "final_arming_state": int(self.status.arming_state) if self.status else None,
                "final_nav_state": int(self.status.nav_state) if self.status else None,
                "external_mode_id": self.external_mode_id,
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

            if self.scenario == "monitor":
                if self.armed_seen and self.status is not None and int(self.status.arming_state) != int(
                    VehicleStatus.ARMING_STATE_ARMED
                ):
                    self._finish("PASS", "armed-to-disarmed sequence observed")
                return

            if self.state == "WAIT_FOR_FMU":
                position_ready = self.local_position is not None and bool(self.local_position.xy_valid)
                registration_ready = self.scenario != "external" or self.external_mode_id is not None
                if self.status is not None and position_ready and registration_ready:
                    self._transition("ARM")
                return

            assert self.status is not None
            armed = int(self.status.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)

            if self.state == "ARM":
                self._command_periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if armed:
                    self._transition("TAKEOFF")
                return

            if self.state == "TAKEOFF":
                self._command_periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                airborne = self.local_position is not None and float(self.local_position.z) < -2.0
                if airborne:
                    target = "OFFBOARD_PRESTREAM" if self.scenario == "offboard" else "ACTIVATE_EXTERNAL"
                    self._transition(target)
                return

            if self.state == "OFFBOARD_PRESTREAM":
                assert self.offboard is not None
                elapsed = now - self.state_started
                self.offboard.publish(self.core.command_at(0.0, elapsed), self._timestamp_us())
                if elapsed >= 1.0:
                    self.offboard.request_mode(producer_timestamp_us=self._timestamp_us())
                if int(self.status.nav_state) == int(VehicleStatus.NAVIGATION_STATE_OFFBOARD):
                    self.active_started = now
                    self._transition("ACTIVE_OFFBOARD")
                return

            if self.state == "ACTIVE_OFFBOARD":
                assert self.offboard is not None
                elapsed = now - self.active_started
                if int(self.status.nav_state) != int(VehicleStatus.NAVIGATION_STATE_OFFBOARD):
                    self._finish("FAIL", "Offboard route exited before release")
                    return
                active_duration = self.active_duration_s or (
                    self.core.hover_seconds + self.core.straight_seconds
                )
                if elapsed < active_duration:
                    command_elapsed = 0.0 if self.hover_only else elapsed
                    self.offboard.publish(
                        self.core.command_at(command_elapsed, elapsed), self._timestamp_us()
                    )
                else:
                    self.offboard.publish(self.core.mission_complete(elapsed), self._timestamp_us())
                    self.offboard.release(self._timestamp_us())
                    self._transition("RELEASE_OFFBOARD")
                return

            if self.state == "RELEASE_OFFBOARD":
                assert self.offboard is not None
                self.offboard.release(self._timestamp_us())
                if int(self.status.nav_state) != int(VehicleStatus.NAVIGATION_STATE_OFFBOARD):
                    self._transition("RTL")
                return

            if self.state == "ACTIVATE_EXTERNAL":
                assert self.external_mode_id is not None
                self._command_periodic(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE, param1=float(self.external_mode_id)
                )
                if int(self.status.nav_state) == self.external_mode_id:
                    self.active_started = now
                    self._transition("ACTIVE_EXTERNAL")
                return

            if self.state == "ACTIVE_EXTERNAL":
                elapsed = now - self.active_started
                active_duration = self.active_duration_s or self.core.duration_seconds
                if elapsed < active_duration - 0.5 and int(self.status.nav_state) != self.external_mode_id:
                    self._finish("FAIL", "registered External Mode exited before completion")
                    return
                if elapsed >= active_duration + 0.25:
                    self._transition("REQUEST_HOLD_AFTER_COMPLETION")
                return

            if self.state == "REQUEST_HOLD_AFTER_COMPLETION":
                self._command_periodic(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
                if int(self.status.nav_state) == int(
                    VehicleStatus.NAVIGATION_STATE_AUTO_LOITER
                ):
                    self._transition("RTL")
                return

            if self.state == "RTL":
                self._command_periodic(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
                if self.armed_seen and not armed:
                    if self.post_disarm_capture_s > 0.0:
                        self._transition("POST_DISARM_CLOCK_CAPTURE")
                    else:
                        self._finish("PASS", "normal route handoff completed and vehicle disarmed")
                return

            if self.state == "POST_DISARM_CLOCK_CAPTURE":
                if now - self.state_started >= self.post_disarm_capture_s:
                    self._finish(
                        "PASS",
                        "normal route handoff completed, vehicle disarmed, and clock capture extended",
                    )

    rclpy.init()
    node = Runner()
    while rclpy.ok() and node.exit_code is None:
        rclpy.spin_once(node, timeout_sec=0.2)
    exit_code = node.exit_code if node.exit_code is not None else 1
    node.destroy_node()
    rclpy.shutdown()
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("offboard", "external", "monitor"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--active-duration", type=float)
    parser.add_argument("--hover-only", action="store_true")
    parser.add_argument("--post-disarm-capture", type=float, default=0.0)
    args = parser.parse_args()
    return run(
        args.scenario,
        args.output,
        args.timeout,
        active_duration_s=args.active_duration,
        hover_only=args.hover_only,
        post_disarm_capture_s=args.post_disarm_capture,
    )


if __name__ == "__main__":
    raise SystemExit(main())
