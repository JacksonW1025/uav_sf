#!/usr/bin/env python3
"""Orchestrate a low-risk hover while independently monitoring route loss."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any


def _name(value: object) -> str:
    if isinstance(value, str):
        return value.rstrip("\x00")
    try:
        return bytes(int(item) for item in value).split(b"\0", 1)[0].decode()
    except (TypeError, ValueError):
        return str(value)


def _versioned_topic(base: str, message_type: object) -> str:
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def _tilt_rad(q: list[float]) -> float:
    if len(q) != 4:
        return 0.0
    w, x, y, z = q
    r33 = max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y)))
    return math.acos(r33)


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            RegisterExtComponentReply,
            TimesyncStatus,
            VehicleAngularVelocity,
            VehicleAttitude,
            VehicleCommand,
            VehicleLandDetected,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover - requires the ROS environment
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.control_dir.mkdir(parents=True, exist_ok=True)

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__(f"phase_a2_{args.experiment_kind}_{args.object}_monitor")
            self.events_handle = args.events.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + args.timeout
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.last_command = 0.0
            self.status: Any | None = None
            self.position: Any | None = None
            self.external_mode_id: int | None = None
            self.armed_seen = False
            self.landed = False
            self.active_seen = False
            self.source_mode: int | None = None
            self.ready_monotonic_ns: int | None = None
            self.ready_ros_time_ns: int | None = None
            self.fault: dict[str, Any] | None = None
            self.fallback_monotonic_ns: int | None = None
            self.fallback_ros_time_ns: int | None = None
            self.fallback_nav_state: int | None = None
            self.automatic_fallback = False
            self.monitor_hold_requested = False
            self.nav_transitions: list[dict[str, object]] = []
            self.last_nav_state: int | None = None
            self.initial_altitude_m: float | None = None
            self.minimum_altitude_m: float | None = None
            self.maximum_altitude_m: float | None = None
            self.peak_tilt_rad = 0.0
            self.attitude_sample_count = 0
            self.peak_angular_rate_rad_s: float | None = None
            self.angular_rate_sample_count = 0
            self.physical_measurement_closed = False
            self.exit_code: int | None = None
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            for message_type, topic, callback in (
                (VehicleStatus, "/fmu/out/vehicle_status", self._status),
                (VehicleLandDetected, "/fmu/out/vehicle_land_detected", self._land_detected),
                (VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._position),
                (VehicleAttitude, "/fmu/out/vehicle_attitude", self._attitude),
                (VehicleAngularVelocity, "/fmu/out/vehicle_angular_velocity", self._angular_velocity),
                (TimesyncStatus, "/fmu/out/timesync_status", self._timesync),
                (
                    RegisterExtComponentReply,
                    "/fmu/out/register_ext_component_reply",
                    self._registration,
                ),
            ):
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, qos
                )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.timer = self.create_timer(0.05, self._tick)
            self._event(
                "route_monitor_started",
                experiment_kind=args.experiment_kind,
                object=args.object,
                fault_class=args.fault_class,
                heartbeat_or_health_enabled=args.heartbeat_or_health == "on",
                setpoint_enabled=args.setpoint == "on",
            )

        def _event(self, event_type: str, **fields: object) -> None:
            record = {
                "event_type": event_type,
                "monotonic_ns": time.monotonic_ns(),
                "ros_time_ns": self.get_clock().now().nanoseconds,
                "state": self.state,
                **fields,
            }
            self.events_handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            self.events_handle.flush()

        def _transition(self, state: str) -> None:
            previous = self.state
            self.state = state
            self.state_started = time.monotonic()
            self.last_command = 0.0
            self._event("state_transition", previous=previous, current=state)

        def _status(self, message: Any) -> None:
            self.status = message
            armed = int(message.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)
            self.armed_seen = self.armed_seen or armed
            nav_state = int(message.nav_state)
            if nav_state != self.last_nav_state:
                transition = {
                    "monotonic_ns": time.monotonic_ns(),
                    "ros_time_ns": self.get_clock().now().nanoseconds,
                    "from": self.last_nav_state,
                    "to": nav_state,
                    "failsafe": bool(message.failsafe),
                }
                self.nav_transitions.append(transition)
                self._event("nav_state_transition", **transition)
                self.last_nav_state = nav_state

            if (
                self.source_mode is not None
                and self.ready_monotonic_ns is not None
                and nav_state != self.source_mode
                and self.fallback_monotonic_ns is None
            ):
                self.fallback_monotonic_ns = time.monotonic_ns()
                self.fallback_ros_time_ns = self.get_clock().now().nanoseconds
                self.fallback_nav_state = nav_state
                self.automatic_fallback = not self.monitor_hold_requested
                self._event(
                    "fallback_selected",
                    source_mode=self.source_mode,
                    fallback_nav_state=nav_state,
                    automatic=self.automatic_fallback,
                    failsafe=bool(message.failsafe),
                )

        def _position(self, message: Any) -> None:
            self.position = message
            if (
                self.ready_monotonic_ns is not None
                and not self.physical_measurement_closed
                and math.isfinite(float(message.z))
            ):
                altitude = -float(message.z)
                if self.initial_altitude_m is None:
                    self.initial_altitude_m = altitude
                self.minimum_altitude_m = (
                    altitude
                    if self.minimum_altitude_m is None
                    else min(self.minimum_altitude_m, altitude)
                )
                self.maximum_altitude_m = (
                    altitude
                    if self.maximum_altitude_m is None
                    else max(self.maximum_altitude_m, altitude)
                )

        def _land_detected(self, message: Any) -> None:
            self.landed = bool(message.landed)

        def _attitude(self, message: Any) -> None:
            if self.ready_monotonic_ns is not None and not self.physical_measurement_closed:
                self.attitude_sample_count += 1
                self.peak_tilt_rad = max(
                    self.peak_tilt_rad, _tilt_rad([float(value) for value in message.q])
                )

        def _angular_velocity(self, message: Any) -> None:
            if self.ready_monotonic_ns is not None and not self.physical_measurement_closed:
                self.angular_rate_sample_count += 1
                values = [float(value) for value in message.xyz]
                magnitude = math.sqrt(sum(value * value for value in values))
                self.peak_angular_rate_rad_s = (
                    magnitude
                    if self.peak_angular_rate_rad_s is None
                    else max(self.peak_angular_rate_rad_s, magnitude)
                )

        def _registration(self, message: Any) -> None:
            if bool(message.success) and _name(message.name) == "Route Transition":
                self.external_mode_id = int(message.mode_id)
                self._event(
                    "external_mode_registration_observed",
                    name="Route Transition",
                    mode_id=self.external_mode_id,
                )

        def _timesync(self, message: Any) -> None:
            receive_ros_ns = self.get_clock().now().nanoseconds
            receive_monotonic_ns = time.monotonic_ns()
            outbound_us = int(message.timestamp)
            offset_us = int(message.estimated_offset)
            self._event(
                "clock_bridge_sample",
                sample_source="timesync_status",
                px4_outbound_timestamp_us=outbound_us,
                px4_boot_timestamp_us=outbound_us + offset_us,
                ros_receive_ns=receive_ros_ns,
                monotonic_receive_ns=receive_monotonic_ns,
                timesync_source_protocol=int(message.source_protocol),
                timesync_estimated_offset_us=offset_us,
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

        def _periodic(self, command: int, period_s: float = 0.5, **params: float) -> None:
            now = time.monotonic()
            if now - self.last_command >= period_s:
                self.last_command = now
                self._command(command, **params)

        def _armed(self) -> bool:
            return self.status is not None and int(self.status.arming_state) == int(
                VehicleStatus.ARMING_STATE_ARMED
            )

        def _source_active(self) -> bool:
            if self.status is None or self.source_mode is None:
                return False
            return int(self.status.nav_state) == self.source_mode

        def _enable_test_channels(self) -> None:
            if args.heartbeat_or_health == "off":
                marker = "heartbeat.off" if args.object == "offboard" else "health_reply.off"
                (args.control_dir / marker).touch()
            if args.setpoint == "off":
                (args.control_dir / "setpoint.off").touch()
            self._event(
                "channel_configuration_applied",
                heartbeat_or_health_enabled=args.heartbeat_or_health == "on",
                setpoint_enabled=args.setpoint == "on",
            )

        def _load_fault(self) -> None:
            if self.fault is None and args.fault_record and args.fault_record.exists():
                self.fault = json.loads(args.fault_record.read_text(encoding="utf-8"))
                self._event("fault_record_observed", fault_record=self.fault)

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            altitude_loss = None
            if self.initial_altitude_m is not None and self.minimum_altitude_m is not None:
                altitude_loss = max(0.0, self.initial_altitude_m - self.minimum_altitude_m)
            detection_latency_ms = None
            if self.fault is not None and self.fallback_monotonic_ns is not None:
                detection_latency_ms = (
                    self.fallback_monotonic_ns - int(self.fault["monotonic_ns"])
                ) / 1_000_000
            result = {
                "schema_version": "1.0",
                "experiment_kind": args.experiment_kind,
                "object": args.object,
                "fault_class": args.fault_class,
                "heartbeat_or_health_enabled": args.heartbeat_or_health == "on",
                "setpoint_enabled": args.setpoint == "on",
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "source_mode": self.source_mode,
                "external_mode_id": self.external_mode_id,
                "active_seen": self.active_seen,
                "experiment_window_monotonic_ns": self.ready_monotonic_ns,
                "experiment_window_ros_time_ns": self.ready_ros_time_ns,
                "fault": self.fault,
                "automatic_fallback_observed": self.automatic_fallback,
                "fallback_nav_state": self.fallback_nav_state,
                "fallback_monotonic_ns": self.fallback_monotonic_ns,
                "fallback_ros_time_ns": self.fallback_ros_time_ns,
                "failure_detection_latency_ms": detection_latency_ms,
                "nav_state_transitions": self.nav_transitions,
                "physical_recovery": {
                    "initial_altitude_m": self.initial_altitude_m,
                    "minimum_altitude_m": self.minimum_altitude_m,
                    "maximum_altitude_m": self.maximum_altitude_m,
                    "altitude_loss_m": altitude_loss,
                    "peak_tilt_rad": self.peak_tilt_rad,
                    "attitude_sample_count": self.attitude_sample_count,
                    "attitude_measurement_status": "AVAILABLE"
                    if self.attitude_sample_count
                    else "UNKNOWN_NO_SAMPLES",
                    "peak_angular_rate_rad_s": self.peak_angular_rate_rad_s,
                    "angular_rate_sample_count": self.angular_rate_sample_count,
                    "angular_rate_measurement_status": "AVAILABLE"
                    if self.angular_rate_sample_count
                    else "UNKNOWN_NOT_PUBLISHED_BY_LOCKED_DDS_CONFIG",
                    "landed": self.landed,
                    "landed_and_disarmed": self.landed and self.armed_seen and not self._armed(),
                },
            }
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            self._event("route_monitor_finished", **result)
            self.events_handle.close()
            self.exit_code = 0 if status == "PASS" else 1
            self.timer.cancel()

        def _tick(self) -> None:
            now = time.monotonic()
            if now >= self.deadline:
                self._finish("FAIL", f"timeout in {self.state}")
                return
            if self.state == "WAIT_FOR_FMU":
                position_ready = self.position is not None and bool(self.position.xy_valid)
                registration_ready = args.object != "external" or self.external_mode_id is not None
                if self.status is not None and position_ready and registration_ready:
                    self._transition("ARM")
                return
            if self.state == "ARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self._transition("TAKEOFF")
                return
            if self.state == "TAKEOFF":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if self.position is not None and float(self.position.z) < -2.0:
                    if args.object == "offboard":
                        (args.control_dir / "activate").touch()
                        self.source_mode = int(VehicleStatus.NAVIGATION_STATE_OFFBOARD)
                        self._transition("WAIT_SOURCE_ACTIVE")
                    else:
                        self.source_mode = self.external_mode_id
                        self._transition("ACTIVATE_EXTERNAL")
                return
            if self.state == "ACTIVATE_EXTERNAL":
                assert self.external_mode_id is not None
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(self.external_mode_id),
                )
                if self._source_active():
                    self.active_seen = True
                    self._transition("STABILIZE")
                return
            if self.state == "WAIT_SOURCE_ACTIVE":
                if self._source_active():
                    self.active_seen = True
                    self._transition("STABILIZE")
                return
            if self.state == "STABILIZE":
                if not self._source_active():
                    self._finish("FAIL", "source route exited before injection window")
                elif now - self.state_started >= (
                    15.0 if args.experiment_kind == "p3" else 3.0
                ):
                    self.ready_monotonic_ns = time.monotonic_ns()
                    self.ready_ros_time_ns = self.get_clock().now().nanoseconds
                    self.initial_altitude_m = -float(self.position.z) if self.position else None
                    if args.experiment_kind == "p3":
                        self._enable_test_channels()
                    args.ready_marker.touch()
                    self._event(
                        "experiment_window_started",
                        source_mode=self.source_mode,
                        ready_monotonic_ns=self.ready_monotonic_ns,
                        ready_ros_time_ns=self.ready_ros_time_ns,
                    )
                    self._transition("OBSERVE")
                return
            if self.state == "OBSERVE":
                self._load_fault()
                elapsed = now - self.state_started
                required = 5.0 if args.experiment_kind == "p2" else args.observe_seconds
                fault_record_ready = args.experiment_kind != "p2" or self.fault is not None
                if fault_record_ready and (
                    self.fallback_monotonic_ns is not None or elapsed >= required
                ):
                    self.physical_measurement_closed = True
                    # Producer shutdown is cleanup after the fixed observation
                    # window, never the mechanism used to create a P3 channel state.
                    (args.control_dir / "stop").touch()
                    self.monitor_hold_requested = True
                    self._transition("REQUEST_HOLD")
                return
            if self.state == "REQUEST_HOLD":
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
                ):
                    if args.experiment_kind == "p3":
                        self._finish("PASS", "P3 observation completed and internal Hold installed")
                    else:
                        self._transition("CLEANUP_LAND")
                elif now - self.state_started >= 2.0:
                    if args.experiment_kind == "p3":
                        self._finish("PASS", "P3 observation completed after bounded cleanup handoff")
                    else:
                        self._transition("CLEANUP_LAND")
                return
            if self.state == "CLEANUP_LAND":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_LAND, period_s=5.0)
                if self.landed:
                    self._finish("PASS", "route experiment completed and vehicle landed")

    rclpy.init()
    node = Monitor()
    while rclpy.ok() and node.exit_code is None:
        rclpy.spin_once(node, timeout_sec=0.1)
    result = node.exit_code if node.exit_code is not None else 1
    node.destroy_node()
    rclpy.shutdown()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-kind", choices=("p2", "p3"), required=True)
    parser.add_argument("--object", choices=("offboard", "external"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--ready-marker", type=Path, required=True)
    parser.add_argument("--fault-record", type=Path)
    parser.add_argument("--fault-class", choices=("sigterm", "sigkill", "sigstop_sigcont"))
    parser.add_argument("--heartbeat-or-health", choices=("on", "off"), default="on")
    parser.add_argument("--setpoint", choices=("on", "off"), default="on")
    parser.add_argument("--observe-seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=150.0)
    args = parser.parse_args()
    if args.experiment_kind == "p2" and (args.fault_record is None or args.fault_class is None):
        parser.error("P2 requires --fault-record and --fault-class")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
