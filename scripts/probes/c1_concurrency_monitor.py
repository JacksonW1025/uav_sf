#!/usr/bin/env python3
"""Run one bounded concurrent-authority event pair in locally owned PX4 SITL."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
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
    _, x, y, _ = q
    return math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y))))


PAIR_EVENTS = {
    "A": ("external_activation", "gcs_hold"),
    "B": ("external_completion", "gcs_takeover_hold"),
    "C": ("local_process_termination", "gcs_rtl"),
    "D": ("automatic_fallback_installation", "external_reentry_request"),
    "E": ("external_release", "failsafe_clear"),
}
CLOCK_PREFLIGHT_WARMUP_SAMPLES = 10


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            FailsafeFlags,
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
        raise SystemExit(f"C1 ROS workspace is required: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.control_dir.mkdir(parents=True, exist_ok=True)

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__(f"c1_{args.pair.lower()}_{args.order.lower()}_monitor")
            self.events_handle = args.events.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + args.timeout
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.last_command = 0.0
            self.status: Any | None = None
            self.position: Any | None = None
            self.land: Any | None = None
            self.external_mode_id: int | None = None
            self.armed_seen = False
            self.active_seen = False
            self.mode_pid: int | None = None
            self.input_events: list[dict[str, Any]] = []
            self.pair_started = 0.0
            self.pending_event: str | None = None
            self.pending_deadline = 0.0
            self.final_snapshot: dict[str, Any] | None = None
            self.health_paused = False
            self.fallback_seen = False
            self.fallback_event_recorded = False
            self.safety_reason: str | None = None
            self.peak_tilt_rad = 0.0
            self.peak_rate_rad_s = 0.0
            self.clock_samples = 0
            self.exit_code: int | None = None
            self.nav_transitions: list[dict[str, Any]] = []
            self.last_nav_state: int | None = None
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            for message_type, topic, callback in (
                (VehicleStatus, "/fmu/out/vehicle_status", self._status),
                (VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._position),
                (VehicleLandDetected, "/fmu/out/vehicle_land_detected", self._land),
                (VehicleAttitude, "/fmu/out/vehicle_attitude", self._attitude),
                (VehicleAngularVelocity, "/fmu/out/vehicle_angular_velocity", self._rate),
                (TimesyncStatus, "/fmu/out/timesync_status", self._timesync),
                (FailsafeFlags, "/fmu/out/failsafe_flags", self._failsafe_flags),
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
            self._event("c1_monitor_started", pair=args.pair, timing_order=args.order)

        def _event(self, event_type: str, **fields: object) -> dict[str, Any]:
            record = {
                "event_type": event_type,
                "monotonic_ns": time.monotonic_ns(),
                "ros_time_ns": self.get_clock().now().nanoseconds,
                "state": self.state,
                **fields,
            }
            self.events_handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            self.events_handle.flush()
            return record

        def _transition(self, state: str) -> None:
            previous = self.state
            self.state = state
            self.state_started = time.monotonic()
            self.last_command = 0.0
            self._event("c1_state_transition", previous=previous, current=state)

        def _status(self, message: Any) -> None:
            self.status = message
            armed = int(message.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)
            self.armed_seen = self.armed_seen or armed
            nav_state = int(message.nav_state)
            if nav_state != self.last_nav_state:
                record = self._event(
                    "nav_state_transition",
                    previous=self.last_nav_state,
                    current=nav_state,
                    executor_in_charge=int(getattr(message, "executor_in_charge", 0)),
                    failsafe=bool(message.failsafe),
                )
                self.nav_transitions.append(record)
                if (
                    self.health_paused
                    and self.external_mode_id is not None
                    and self.last_nav_state == self.external_mode_id
                    and nav_state != self.external_mode_id
                ):
                    self.fallback_seen = True
                    self._event(
                        "automatic_fallback_observed",
                        source_mode=self.external_mode_id,
                        fallback_nav_state=nav_state,
                    )
                self.last_nav_state = nav_state

        def _position(self, message: Any) -> None:
            self.position = message

        def _land(self, message: Any) -> None:
            self.land = message
            if (
                self.state not in {"WAIT_FOR_FMU", "ARM", "TAKEOFF", "CLEANUP"}
                and bool(message.ground_contact)
                and self.armed_seen
                and self.safety_reason is None
            ):
                self._safety_stop("unexpected_ground_contact_before_cleanup")

        def _attitude(self, message: Any) -> None:
            self.peak_tilt_rad = max(
                self.peak_tilt_rad, _tilt_rad([float(value) for value in message.q])
            )
            if math.degrees(self.peak_tilt_rad) > 45.0 and self.safety_reason is None:
                self._safety_stop("attitude_safety_bound_exceeded")

        def _rate(self, message: Any) -> None:
            values = [float(value) for value in message.xyz]
            self.peak_rate_rad_s = max(
                self.peak_rate_rad_s, math.sqrt(sum(value * value for value in values))
            )
            if self.peak_rate_rad_s > 3.0 and self.safety_reason is None:
                self._safety_stop("angular_rate_safety_bound_exceeded")

        def _timesync(self, message: Any) -> None:
            self.clock_samples += 1
            self._event(
                "clock_bridge_sample",
                sample_source="timesync_status",
                px4_outbound_timestamp_us=int(message.timestamp),
                px4_boot_timestamp_us=int(message.timestamp) + int(message.estimated_offset),
                ros_receive_ns=self.get_clock().now().nanoseconds,
                monotonic_receive_ns=time.monotonic_ns(),
                timesync_source_protocol=int(message.source_protocol),
                timesync_estimated_offset_us=int(message.estimated_offset),
                timesync_round_trip_time_us=int(message.round_trip_time),
                timesync_converged=int(message.source_protocol) == 2,
            )

        def _failsafe_flags(self, message: Any) -> None:
            self._event(
                "failsafe_flags_observed",
                mode_req_other=bool(getattr(message, "mode_req_other", False)),
            )

        def _registration(self, message: Any) -> None:
            if bool(message.success) and _name(message.name) == "C1 Concurrency Probe":
                self.external_mode_id = int(message.mode_id)
                self._event(
                    "external_mode_registration_observed",
                    mode_id=self.external_mode_id,
                    name="C1 Concurrency Probe",
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

        def _periodic(self, command: int, period_s: float = 0.5, **params: float) -> None:
            now = time.monotonic()
            if now - self.last_command >= period_s:
                self.last_command = now
                self._command(command, **params)

        def _read_mode_pid(self) -> int:
            if self.mode_pid is not None:
                return self.mode_pid
            value = args.mode_pid_file.read_text(encoding="utf-8").strip()
            self.mode_pid = int(value)
            return self.mode_pid

        def _record_input(self, name: str, origin: str = "public_interface") -> None:
            if any(record["pair_event"] == name for record in self.input_events):
                return
            record = self._event(
                "c1_input_event",
                pair_event=name,
                origin=origin,
                ordinal=len(self.input_events) + 1,
            )
            self.input_events.append(record)

        def _trigger(self, name: str) -> None:
            self._record_input(name)
            if name in {"external_activation", "external_reentry_request"}:
                assert self.external_mode_id is not None
                if name == "external_reentry_request" and self.fallback_seen:
                    (args.control_dir / "health_reply.off").unlink(missing_ok=True)
                self._command(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(self.external_mode_id),
                )
            elif name in {"gcs_hold", "gcs_takeover_hold"}:
                self._command(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
            elif name == "external_completion":
                (args.control_dir / "completion.request").touch()
            elif name == "local_process_termination":
                os.kill(self._read_mode_pid(), signal.SIGKILL)
            elif name == "gcs_rtl":
                self._command(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
            elif name == "external_release":
                os.kill(self._read_mode_pid(), signal.SIGTERM)
            elif name == "failsafe_clear":
                (args.control_dir / "health_reply.off").unlink(missing_ok=True)
                self.health_paused = False
            else:
                raise RuntimeError(f"unsupported C1 pair event: {name}")

        def _start_generic_pair(self) -> None:
            event_a, event_b = PAIR_EVENTS[args.pair]
            self.pair_started = time.monotonic()
            self._event("c1_pair_window_started", event_a=event_a, event_b=event_b)
            if args.order == "A_FIRST":
                self._trigger(event_a)
                self.pending_event = event_b
                self.pending_deadline = self.pair_started + 0.4
            elif args.order == "B_FIRST":
                self._trigger(event_b)
                self.pending_event = event_a
                self.pending_deadline = self.pair_started + 0.4
            else:
                self._trigger(event_a)
                self._trigger(event_b)
            self._transition("PAIR_RUNNING")

        def _pause_health(self, next_state: str) -> None:
            (args.control_dir / "health_reply.off").touch()
            self.health_paused = True
            self._event("health_channel_paused")
            self._transition(next_state)

        def _start_d(self) -> None:
            self.pair_started = time.monotonic()
            self._event(
                "c1_pair_window_started",
                event_a=PAIR_EVENTS["D"][0],
                event_b=PAIR_EVENTS["D"][1],
            )
            self._pause_health("WAIT_D_FALLBACK")

        def _record_fallback_pair_event(self) -> None:
            if self.fallback_event_recorded:
                return
            self.fallback_event_recorded = True
            self._record_input("automatic_fallback_installation", origin="automatic_fallback")

        def _close_pair_window(self) -> None:
            assert self.status is not None
            self.final_snapshot = {
                "nav_state": int(self.status.nav_state),
                "executor_in_charge": int(getattr(self.status, "executor_in_charge", 0)),
                "failsafe": bool(self.status.failsafe),
                "armed": int(self.status.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED),
            }
            self._event("linearization_window_closed", **self.final_snapshot)
            self._transition("CLEANUP")

        def _safety_stop(self, reason: str) -> None:
            self.safety_reason = reason
            self._event("formal_safety_stop", reason=reason)
            self._transition("CLEANUP")

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "run_id": args.run_id,
                "pair": args.pair,
                "timing_order": args.order,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "external_mode_id": self.external_mode_id,
                "input_events": [
                    {
                        "name": record["pair_event"],
                        "monotonic_ns": record["monotonic_ns"],
                        "ros_time_ns": record["ros_time_ns"],
                        "origin": record["origin"],
                    }
                    for record in self.input_events
                ],
                "linearization_final": self.final_snapshot,
                "cleanup": {
                    "landed": bool(self.land.landed) if self.land is not None else None,
                    "disarmed": self.status is not None
                    and int(self.status.arming_state) != int(VehicleStatus.ARMING_STATE_ARMED),
                },
                "physical": {
                    "maximum_tilt_deg": math.degrees(self.peak_tilt_rad),
                    "maximum_angular_rate_rad_s": self.peak_rate_rad_s,
                },
                "clock_sample_count": self.clock_samples,
                "nav_transition_count": len(self.nav_transitions),
                "safety_reason": self.safety_reason,
            }
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            self._event("c1_monitor_finished", **result)
            self.events_handle.close()
            self.exit_code = 0 if status == "PASS" else 1
            self.timer.cancel()

        def _tick(self) -> None:
            now = time.monotonic()
            if now >= self.deadline:
                self._finish("ENVIRONMENT_FAILURE", f"timeout in {self.state}")
                return
            if self.status is None:
                return
            armed = int(self.status.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)
            nav_state = int(self.status.nav_state)
            hold_state = int(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER)
            rtl_state = int(VehicleStatus.NAVIGATION_STATE_AUTO_RTL)

            if self.state == "WAIT_FOR_FMU":
                ready = (
                    self.position is not None
                    and bool(self.position.xy_valid)
                    and self.external_mode_id is not None
                    and args.mode_pid_file.exists()
                    and self.clock_samples >= CLOCK_PREFLIGHT_WARMUP_SAMPLES
                )
                if ready:
                    self._transition("ARM")
                return
            if self.state == "ARM":
                self._periodic(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                if armed:
                    self._transition("TAKEOFF")
                return
            if self.state == "TAKEOFF":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                if self.position is not None and float(self.position.z) < -2.0:
                    self._transition("PREP_HOLD")
                return
            if self.state == "PREP_HOLD":
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                    param1=1.0,
                    param2=4.0,
                    param3=3.0,
                )
                if nav_state == hold_state:
                    if args.pair == "A":
                        self._start_generic_pair()
                    else:
                        self._transition("ACTIVATE_EXTERNAL")
                return
            if self.state == "ACTIVATE_EXTERNAL":
                assert self.external_mode_id is not None
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(self.external_mode_id),
                )
                if nav_state == self.external_mode_id:
                    self.active_seen = True
                    self._transition("STABILIZE_EXTERNAL")
                return
            if self.state == "STABILIZE_EXTERNAL":
                if nav_state != self.external_mode_id:
                    self._finish("ENVIRONMENT_FAILURE", "external route exited before pair")
                elif now - self.state_started >= 1.0:
                    if args.pair == "D":
                        self._start_d()
                    elif args.pair == "E":
                        self._pause_health("WAIT_E_FALLBACK")
                    else:
                        self._start_generic_pair()
                return
            if self.state == "WAIT_D_FALLBACK":
                if args.order == "B_FIRST" and not self.input_events and now - self.state_started >= 0.75:
                    self._trigger("external_reentry_request")
                if self.fallback_seen:
                    self._record_fallback_pair_event()
                    if args.order in {"A_FIRST", "NEAR_SIMULTANEOUS"}:
                        if args.order == "NEAR_SIMULTANEOUS":
                            self._trigger("external_reentry_request")
                        else:
                            self.pending_event = "external_reentry_request"
                            self.pending_deadline = now + 0.4
                    self._transition("PAIR_RUNNING")
                return
            if self.state == "WAIT_E_FALLBACK":
                if self.fallback_seen:
                    self._start_generic_pair()
                return
            if self.state == "PAIR_RUNNING":
                if self.pending_event is not None and now >= self.pending_deadline:
                    event = self.pending_event
                    self.pending_event = None
                    self._trigger(event)
                if len(self.input_events) == 2 and self.pending_event is None:
                    last_ns = max(record["monotonic_ns"] for record in self.input_events)
                    if time.monotonic_ns() - last_ns >= 1_500_000_000:
                        self._close_pair_window()
                return
            if self.state == "CLEANUP":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
                if self.armed_seen and not armed:
                    status = "FORMAL_SAFETY_STOP" if self.safety_reason else "PASS"
                    reason = self.safety_reason or "pair observed and Land/Disarm cleanup complete"
                    self._finish(status, reason)

    rclpy.init()
    node = Monitor()
    while rclpy.ok() and node.exit_code is None:
        rclpy.spin_once(node, timeout_sec=0.1)
    exit_code = node.exit_code if node.exit_code is not None else 1
    node.destroy_node()
    rclpy.shutdown()
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pair", choices=tuple(PAIR_EVENTS), required=True)
    parser.add_argument(
        "--order", choices=("A_FIRST", "NEAR_SIMULTANEOUS", "B_FIRST"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--mode-pid-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
