#!/usr/bin/env python3
"""Drive and safety-monitor one bounded B1 registered-controller flight."""

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


def _roll_pitch(q: object) -> tuple[float, float]:
    w, x, y, z = (float(q[index]) for index in range(4))
    sinr = 2.0 * (w * x + y * z)
    cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)
    sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    return roll, math.asin(sinp)


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            ActuatorMotors,
            RegisterExtComponentReply,
            TimesyncStatus,
            VehicleAngularVelocity,
            VehicleAttitude,
            VehicleAttitudeSetpoint,
            VehicleCommand,
            VehicleLandDetected,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover - requires locked ROS workspace
        raise SystemExit(f"locked ROS workspace is required: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.control_dir.mkdir(parents=True, exist_ok=True)

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__(f"b1_{args.run_id.replace('-', '_')}_monitor")
            self.events_handle = args.events.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + args.timeout
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.last_command = 0.0
            self.status: Any | None = None
            self.position: Any | None = None
            self.external_mode_id: int | None = None
            self.last_nav_state: int | None = None
            self.landed = False
            self.safety_reason: str | None = None
            self.reference_output_count = 0
            self.actuator_output_count = 0
            self.clock_sample_count = 0
            self.timesync_estimated_offset_us: int | None = None
            self.timesync_round_trip_time_us: int | None = None
            self.timesync_source_protocol: int | None = None
            self.reference_window_start_ns: int | None = None
            self.release_request_ns: int | None = None
            self.restoration_ns: int | None = None
            self.maxima = {
                "altitude_agl_m": 0.0,
                "horizontal_distance_m": 0.0,
                "speed_m_s": 0.0,
                "attitude_deg": 0.0,
                "angular_rate_rad_s": 0.0,
                "controller_output_abs": 0.0,
                "actuator_output_abs": 0.0,
            }
            self.telemetry_counts = {
                "position": 0,
                "attitude": 0,
                "angular_velocity": 0,
                "reference_output": 0,
                "actuator_output": 0,
            }
            self.exit_code: int | None = None
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            subscriptions = (
                (VehicleStatus, "/fmu/out/vehicle_status", self._status),
                (VehicleLandDetected, "/fmu/out/vehicle_land_detected", self._land),
                (VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._position),
                (VehicleAttitude, "/fmu/out/vehicle_attitude", self._attitude),
                (VehicleAngularVelocity, "/fmu/out/vehicle_angular_velocity", self._angular),
                (VehicleAttitudeSetpoint, "/fmu/out/vehicle_attitude_setpoint", self._setpoint),
                (ActuatorMotors, "/fmu/out/actuator_motors", self._actuators),
                (TimesyncStatus, "/fmu/out/timesync_status", self._timesync),
                (RegisterExtComponentReply, "/fmu/out/register_ext_component_reply", self._registration),
            )
            for message_type, topic, callback in subscriptions:
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, qos
                )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.timer = self.create_timer(0.05, self._tick)
            self._event(
                "b1_monitor_started",
                release_kind=args.release_kind,
                safety_bounds={
                    "altitude_agl_m": args.maximum_altitude,
                    "horizontal_distance_m": args.maximum_horizontal_distance,
                    "speed_m_s": args.maximum_speed,
                    "attitude_deg": args.maximum_attitude_deg,
                    "angular_rate_rad_s": args.maximum_angular_rate,
                    "output_abs": args.maximum_output,
                },
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

        def _armed(self) -> bool:
            return self.status is not None and int(self.status.arming_state) == int(
                VehicleStatus.ARMING_STATE_ARMED
            )

        def _reference_active(self) -> bool:
            return (
                self.status is not None
                and self.external_mode_id is not None
                and int(self.status.nav_state) == self.external_mode_id
            )

        def _safety_stop(self, reason: str, **fields: object) -> None:
            if self.safety_reason is not None:
                return
            self.safety_reason = reason
            self._event("formal_safety_stop", reason=reason, **fields)
            self._transition("CLEANUP_LAND")

        def _status(self, message: Any) -> None:
            self.status = message
            nav_state = int(message.nav_state)
            if nav_state != self.last_nav_state:
                self._event(
                    "nav_state_transition",
                    previous=self.last_nav_state,
                    current=nav_state,
                    failsafe=bool(message.failsafe),
                )
                self.last_nav_state = nav_state

        def _land(self, message: Any) -> None:
            self.landed = bool(message.landed)

        def _position(self, message: Any) -> None:
            self.position = message
            self.telemetry_counts["position"] += 1
            values = [float(message.x), float(message.y), float(message.z),
                      float(message.vx), float(message.vy), float(message.vz)]
            if not all(math.isfinite(value) for value in values):
                self._safety_stop("nonfinite_position_or_velocity")
                return
            altitude = max(0.0, -float(message.z))
            distance = math.hypot(float(message.x), float(message.y))
            speed = math.sqrt(float(message.vx) ** 2 + float(message.vy) ** 2 + float(message.vz) ** 2)
            self.maxima["altitude_agl_m"] = max(self.maxima["altitude_agl_m"], altitude)
            self.maxima["horizontal_distance_m"] = max(self.maxima["horizontal_distance_m"], distance)
            self.maxima["speed_m_s"] = max(self.maxima["speed_m_s"], speed)
            if altitude > args.maximum_altitude:
                self._safety_stop("altitude_bound_exceeded", observed=altitude)
            elif distance > args.maximum_horizontal_distance:
                self._safety_stop("horizontal_distance_bound_exceeded", observed=distance)
            elif self.state in {"CLASSIC_STABLE", "ACTIVATE_REFERENCE", "REFERENCE_STABLE", "WAIT_INTERRUPTION", "RECOVERY"} and speed > args.maximum_speed:
                self._safety_stop("speed_bound_exceeded", observed=speed)
            self._clock_sample(int(message.timestamp), "vehicle_local_position")

        def _attitude(self, message: Any) -> None:
            self.telemetry_counts["attitude"] += 1
            try:
                roll, pitch = _roll_pitch(message.q)
            except (ValueError, TypeError):
                self._safety_stop("invalid_attitude")
                return
            angle = math.degrees(max(abs(roll), abs(pitch)))
            if not math.isfinite(angle):
                self._safety_stop("nonfinite_attitude")
                return
            self.maxima["attitude_deg"] = max(self.maxima["attitude_deg"], angle)
            if angle > args.maximum_attitude_deg:
                self._safety_stop("attitude_bound_exceeded", observed=angle)

        def _angular(self, message: Any) -> None:
            self.telemetry_counts["angular_velocity"] += 1
            values = [float(value) for value in message.xyz]
            if not all(math.isfinite(value) for value in values):
                self._safety_stop("nonfinite_angular_rate")
                return
            rate = math.sqrt(sum(value * value for value in values))
            self.maxima["angular_rate_rad_s"] = max(self.maxima["angular_rate_rad_s"], rate)
            if rate > args.maximum_angular_rate:
                self._safety_stop("angular_rate_bound_exceeded", observed=rate)

        def _setpoint(self, message: Any) -> None:
            if not self._reference_active():
                return
            values = [float(value) for value in message.thrust_body]
            if not all(math.isfinite(value) for value in values):
                self._safety_stop("nonfinite_reference_output")
                return
            magnitude = max(abs(value) for value in values)
            self.maxima["controller_output_abs"] = max(
                self.maxima["controller_output_abs"], magnitude
            )
            self.reference_output_count += 1
            self.telemetry_counts["reference_output"] += 1
            if magnitude > args.maximum_output:
                self._safety_stop("controller_output_bound_exceeded", observed=magnitude)

        def _actuators(self, message: Any) -> None:
            values = [float(value) for value in message.control[:4]]
            finite = [value for value in values if math.isfinite(value)]
            if len(finite) != 4:
                self._safety_stop("nonfinite_primary_actuator_output")
                return
            magnitude = max(abs(value) for value in finite)
            self.maxima["actuator_output_abs"] = max(
                self.maxima["actuator_output_abs"], magnitude
            )
            self.actuator_output_count += 1
            self.telemetry_counts["actuator_output"] += 1
            if magnitude > args.maximum_output:
                self._safety_stop("actuator_output_bound_exceeded", observed=magnitude)

        def _registration(self, message: Any) -> None:
            if bool(message.success) and _name(message.name) == "B1 Reference":
                self.external_mode_id = int(message.mode_id)
                self._event(
                    "b1_registration_observed",
                    mode_id=self.external_mode_id,
                    arming_check_id=int(message.arming_check_id),
                    request_id=int(message.request_id),
                )

        def _timesync(self, message: Any) -> None:
            self.timesync_estimated_offset_us = int(message.estimated_offset)
            self.timesync_round_trip_time_us = int(message.round_trip_time)
            self.timesync_source_protocol = int(message.source_protocol)
            self._clock_sample(int(message.timestamp), "timesync_status")

        def _clock_sample(self, outbound_us: int, source: str) -> None:
            if self.timesync_estimated_offset_us is None or self.timesync_round_trip_time_us is None or self.timesync_source_protocol is None:
                return
            self.clock_sample_count += 1
            self._event(
                "clock_bridge_sample",
                sample_source=source,
                px4_outbound_timestamp_us=outbound_us,
                px4_boot_timestamp_us=outbound_us + self.timesync_estimated_offset_us,
                ros_receive_ns=self.get_clock().now().nanoseconds,
                monotonic_receive_ns=time.monotonic_ns(),
                timesync_source_protocol=self.timesync_source_protocol,
                timesync_estimated_offset_us=self.timesync_estimated_offset_us,
                timesync_round_trip_time_us=self.timesync_round_trip_time_us,
                timesync_converged=self.timesync_source_protocol == 2,
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

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "run_id": args.run_id,
                "release_kind": args.release_kind,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "external_mode_id": self.external_mode_id,
                "classic_mode_id": int(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER),
                "safety_stop_reason": self.safety_reason,
                "reference_window_start_ns": self.reference_window_start_ns,
                "release_request_ns": self.release_request_ns,
                "restoration_ns": self.restoration_ns,
                "reference_output_count": self.reference_output_count,
                "actuator_output_count": self.actuator_output_count,
                "clock_sample_count": self.clock_sample_count,
                "telemetry_counts": self.telemetry_counts,
                "maxima": self.maxima,
                "landed": self.landed,
                "armed_at_finish": self._armed(),
            }
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._event("b1_monitor_finished", **result)
            self.events_handle.close()
            self.exit_code = 0 if status == "PASS" else 1
            self.timer.cancel()

        def _tick(self) -> None:
            now = time.monotonic()
            if now >= self.deadline:
                self._safety_stop(f"timeout_in_{self.state}")
            if self.state == "WAIT_FOR_FMU":
                if self.status is not None and self.position is not None and self.external_mode_id is not None:
                    self._transition("ARM")
            elif self.state == "ARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if self._armed():
                    self._transition("TAKEOFF")
            elif self.state == "TAKEOFF":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if self.position is not None and float(self.position.z) < -1.2:
                    self._transition("REQUEST_CLASSIC_HOLD")
            elif self.state == "REQUEST_CLASSIC_HOLD":
                self._periodic(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, param1=1.0, param2=4.0, param3=3.0)
                if self.status is not None and int(self.status.nav_state) == int(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER):
                    self._transition("CLASSIC_STABLE")
            elif self.state == "CLASSIC_STABLE":
                if now - self.state_started >= args.classic_stable_seconds and self.clock_sample_count >= 20:
                    self._transition("ACTIVATE_REFERENCE")
            elif self.state == "ACTIVATE_REFERENCE":
                assert self.external_mode_id is not None
                self._periodic(VehicleCommand.VEHICLE_CMD_SET_NAV_STATE, param1=float(self.external_mode_id))
                if self._reference_active():
                    self.reference_window_start_ns = self.get_clock().now().nanoseconds
                    self._event("reference_route_installed", mode_id=self.external_mode_id)
                    self._transition("REFERENCE_STABLE")
            elif self.state == "REFERENCE_STABLE":
                if not self._reference_active():
                    self._safety_stop("reference_route_exited_before_release")
                elif now - self.state_started >= args.reference_stable_seconds:
                    if self.reference_output_count < 20 or self.actuator_output_count < 20:
                        self._safety_stop("incomplete_reference_or_actuator_window")
                    else:
                        args.ready_marker.touch(exist_ok=False)
                        self.release_request_ns = self.get_clock().now().nanoseconds
                        self._event("reference_release_window_open", release_kind=args.release_kind)
                        self._transition("WAIT_INTERRUPTION" if args.release_kind == "CONTROLLED_STOP" else "REQUEST_NORMAL_RELEASE")
            elif self.state == "REQUEST_NORMAL_RELEASE":
                self._periodic(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, param1=1.0, param2=4.0, param3=3.0)
                if self.status is not None and int(self.status.nav_state) == int(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER):
                    self.restoration_ns = self.get_clock().now().nanoseconds
                    self._event("classic_route_restored", release_kind=args.release_kind)
                    self._transition("RECOVERY")
            elif self.state == "WAIT_INTERRUPTION":
                if args.interruption_record.exists() and not self._reference_active():
                    self.restoration_ns = self.get_clock().now().nanoseconds
                    self._event("classic_route_restored", release_kind=args.release_kind)
                    self._transition("RECOVERY")
            elif self.state == "RECOVERY":
                if self._reference_active():
                    self._safety_stop("reference_route_reentered_after_release")
                elif now - self.state_started >= args.recovery_seconds:
                    self._transition("CLEANUP_LAND")
            elif self.state == "CLEANUP_LAND":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_LAND, period_s=1.0)
                if self.landed:
                    self._transition("CLEANUP_DISARM")
            elif self.state == "CLEANUP_DISARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=0.0)
                if not self._armed():
                    status = "PASS" if self.safety_reason is None else "FORMAL_SAFETY_STOP"
                    self._finish(status, "bounded B1 flight completed and disarmed")

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
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--release-kind", choices=("NORMAL", "CONTROLLED_STOP"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--ready-marker", type=Path, required=True)
    parser.add_argument("--interruption-record", type=Path, required=True)
    parser.add_argument("--classic-stable-seconds", type=float, default=2.0)
    parser.add_argument("--reference-stable-seconds", type=float, default=3.0)
    parser.add_argument("--recovery-seconds", type=float, default=2.0)
    parser.add_argument("--maximum-altitude", type=float, default=3.0)
    parser.add_argument("--maximum-horizontal-distance", type=float, default=4.0)
    parser.add_argument("--maximum-speed", type=float, default=1.0)
    parser.add_argument("--maximum-attitude-deg", type=float, default=30.0)
    parser.add_argument("--maximum-angular-rate", type=float, default=2.0)
    parser.add_argument("--maximum-output", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
