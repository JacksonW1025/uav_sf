#!/usr/bin/env python3
"""Drive one bounded External Mode freshness flight and monitor safe recovery."""

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
    except ImportError as exc:  # pragma: no cover - requires the locked ROS workspace
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.control_dir.mkdir(parents=True, exist_ok=True)

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__(f"freshness_{args.run_id.replace('-', '_')}_monitor")
            self.events_handle = args.events.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + args.timeout
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.last_command = 0.0
            self.status: Any | None = None
            self.position: Any | None = None
            self.external_mode_id: int | None = None
            self.landed = False
            self.armed_seen = False
            self.active_seen = False
            self.last_nav_state: int | None = None
            self.clock_sample_count = 0
            self.telemetry_counts = {"position": 0, "attitude": 0, "angular_velocity": 0}
            self.ready_monotonic_ns: int | None = None
            self.ready_ros_time_ns: int | None = None
            self.fault: dict[str, Any] | None = None
            self.fallback_declared_ros_time_ns: int | None = None
            self.fallback_installed_ros_time_ns: int | None = None
            self.fallback_nav_state: int | None = None
            self.automatic_fallback = False
            self.target_window_end_ros_time_ns: int | None = None
            self.target_window_end_monotonic_ns: int | None = None
            self.target_policy_terminated = False
            self.explicit_cleanup_requested = False
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
                (RegisterExtComponentReply, "/fmu/out/register_ext_component_reply", self._registration),
            ):
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, qos
                )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.timer = self.create_timer(0.05, self._tick)
            self._event(
                "freshness_monitor_started",
                run_id=args.run_id,
                setpoint_type=args.setpoint_type,
                fault_type=args.fault_type,
                stable_seconds=args.stable_seconds,
                target_seconds=args.target_seconds,
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

        def _source_active(self) -> bool:
            return (
                self.status is not None
                and self.external_mode_id is not None
                and int(self.status.nav_state) == self.external_mode_id
            )

        def _status(self, message: Any) -> None:
            self.status = message
            self.armed_seen = self.armed_seen or self._armed()
            nav_state = int(message.nav_state)
            if nav_state != self.last_nav_state:
                self._event(
                    "nav_state_transition",
                    previous=self.last_nav_state,
                    current=nav_state,
                    failsafe=bool(message.failsafe),
                )
                self.last_nav_state = nav_state
            if (
                self.ready_ros_time_ns is not None
                and bool(message.failsafe)
                and self.fallback_declared_ros_time_ns is None
            ):
                self.fallback_declared_ros_time_ns = self.get_clock().now().nanoseconds
                self._event("fallback_declared", nav_state=nav_state)
            if (
                self.ready_ros_time_ns is not None
                and self.external_mode_id is not None
                and nav_state != self.external_mode_id
                and self.fallback_installed_ros_time_ns is None
            ):
                self.fallback_installed_ros_time_ns = self.get_clock().now().nanoseconds
                self.fallback_nav_state = nav_state
                self.automatic_fallback = not self.explicit_cleanup_requested
                self._event(
                    "fallback_installed",
                    fallback_nav_state=nav_state,
                    automatic=self.automatic_fallback,
                    failsafe=bool(message.failsafe),
                )

        def _position(self, message: Any) -> None:
            self.position = message
            self.telemetry_counts["position"] += 1

        def _attitude(self, _: Any) -> None:
            self.telemetry_counts["attitude"] += 1

        def _angular_velocity(self, _: Any) -> None:
            self.telemetry_counts["angular_velocity"] += 1

        def _land_detected(self, message: Any) -> None:
            self.landed = bool(message.landed)

        def _registration(self, message: Any) -> None:
            if bool(message.success) and _name(message.name) == "Freshness Probe":
                self.external_mode_id = int(message.mode_id)
                self._event(
                    "freshness_registration_observed",
                    component_name="Freshness Probe",
                    mode_id=self.external_mode_id,
                    arming_check_id=int(message.arming_check_id),
                )

        def _timesync(self, message: Any) -> None:
            self.clock_sample_count += 1
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

        def _load_fault(self) -> None:
            if self.fault is None and args.fault_record.exists():
                self.fault = json.loads(args.fault_record.read_text(encoding="utf-8"))
                self._event("freshness_fault_record_observed", fault=self.fault)

        def _close_target_window(self, policy_terminated: bool) -> None:
            if self.target_window_end_ros_time_ns is not None:
                return
            self.target_window_end_ros_time_ns = self.get_clock().now().nanoseconds
            self.target_window_end_monotonic_ns = time.monotonic_ns()
            self.target_policy_terminated = policy_terminated
            self._event(
                "pre_revocation_target_window_completed",
                policy_terminated=policy_terminated,
                source_route_retained=self._source_active(),
            )

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "run_id": args.run_id,
                "setpoint_type": args.setpoint_type,
                "fault_type": args.fault_type,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "external_mode_id": self.external_mode_id,
                "active_seen": self.active_seen,
                "clock_sample_count": self.clock_sample_count,
                "telemetry_counts": self.telemetry_counts,
                "ready_monotonic_ns": self.ready_monotonic_ns,
                "ready_ros_time_ns": self.ready_ros_time_ns,
                "fault": self.fault,
                "fallback_declared_ros_time_ns": self.fallback_declared_ros_time_ns,
                "fallback_installed_ros_time_ns": self.fallback_installed_ros_time_ns,
                "fallback_nav_state": self.fallback_nav_state,
                "automatic_fallback_observed": self.automatic_fallback,
                "target_window_end_ros_time_ns": self.target_window_end_ros_time_ns,
                "target_window_end_monotonic_ns": self.target_window_end_monotonic_ns,
                "target_policy_terminated": self.target_policy_terminated,
                "external_route_retained_at_window_end": (
                    args.fault_type == "SETPOINT_ONLY_STALL"
                    and not self.automatic_fallback
                    and self.target_policy_terminated
                ),
                "landed": self.landed,
                "armed_at_finish": self._armed(),
            }
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            self._event("freshness_monitor_finished", **result)
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
                if self.position is not None and float(self.position.z) < -2.0:
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
            if self.state == "STABILIZE":
                if not self._source_active():
                    self._finish("FAIL", "external route exited before the fault window")
                elif (
                    now - self.state_started >= args.stable_seconds
                    and self.clock_sample_count >= args.minimum_clock_samples
                    and self.telemetry_counts["position"] >= 20
                    and self.telemetry_counts["attitude"] >= 20
                ):
                    self.ready_monotonic_ns = time.monotonic_ns()
                    self.ready_ros_time_ns = self.get_clock().now().nanoseconds
                    args.ready_marker.touch(exist_ok=False)
                    self._event(
                        "pre_fault_stable_window_completed",
                        external_mode_id=self.external_mode_id,
                        telemetry_counts=self.telemetry_counts,
                    )
                    self._transition("OBSERVE_TARGET")
                return
            if self.state == "OBSERVE_TARGET":
                self._load_fault()
                if self.fault is None:
                    return
                if args.fault_type == "TOTAL_PROCESS_STOP":
                    if self.fallback_installed_ros_time_ns is not None:
                        self._close_target_window(policy_terminated=False)
                        self._transition("RECOVER")
                else:
                    elapsed = (time.monotonic_ns() - int(self.fault["monotonic_ns"])) / 1e9
                    if not self._source_active():
                        self._finish("FAIL", "health-alive stall lost the external route")
                    elif elapsed >= args.target_seconds:
                        self._close_target_window(policy_terminated=True)
                        self.explicit_cleanup_requested = True
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
                    and int(self.status.nav_state) == int(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER)
                ):
                    self._transition("RECOVER")
                return
            if self.state == "RECOVER":
                if now - self.state_started >= args.recovery_seconds:
                    self._transition("CLEANUP_LAND")
                return
            if self.state == "CLEANUP_LAND":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_LAND, period_s=2.0)
                if self.landed:
                    self._transition("CLEANUP_DISARM")
                return
            if self.state == "CLEANUP_DISARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=0.0)
                if not self._armed():
                    self._finish("PASS", "bounded freshness flight completed and disarmed")

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
    parser.add_argument("--setpoint-type", choices=("TRAJECTORY", "ATTITUDE", "RATE"), required=True)
    parser.add_argument("--fault-type", choices=("TOTAL_PROCESS_STOP", "SETPOINT_ONLY_STALL"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--ready-marker", type=Path, required=True)
    parser.add_argument("--fault-record", type=Path, required=True)
    parser.add_argument("--stable-seconds", type=float, default=2.0)
    parser.add_argument("--target-seconds", type=float, default=3.0)
    parser.add_argument("--recovery-seconds", type=float, default=2.0)
    parser.add_argument("--minimum-clock-samples", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if min(args.stable_seconds, args.target_seconds, args.recovery_seconds) <= 0:
        parser.error("all observation durations must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
