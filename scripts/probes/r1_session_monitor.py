#!/usr/bin/env python3
"""Run one bounded session-rollover scenario in locally owned PX4 SITL."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, TextIO


CLOCK_PREFLIGHT_WARMUP_SAMPLES = 20
SCENARIOS = ("A", "B", "C")


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


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            ModeCompleted,
            RegisterExtComponentRequest,
            RegisterExtComponentReply,
            TimesyncStatus,
            VehicleAngularVelocity,
            VehicleAttitude,
            VehicleCommand,
            VehicleControlMode,
            VehicleLandDetected,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover - requires the ROS environment
        raise SystemExit(f"R1 ROS workspace is required: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.events.parent.mkdir(parents=True, exist_ok=True)
    args.control_dir.mkdir(parents=True, exist_ok=True)

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__(f"r1_{args.scenario.lower()}_monitor")
            self.events_handle = args.events.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + args.timeout
            self.state = "WAIT_FOR_FMU"
            self.state_started = self.started
            self.last_command = 0.0
            self.status: Any | None = None
            self.position: Any | None = None
            self.land: Any | None = None
            self.control_mode: Any | None = None
            self.old_mode_id: int | None = None
            self.old_executor_id: int | None = None
            self.old_registration_request_id: int | None = None
            self.old_registration_reply_request_id: int | None = None
            self.new_mode_id: int | None = None
            self.new_executor_id: int | None = None
            self.new_registration_request_id: int | None = None
            self.new_registration_reply_request_id: int | None = None
            self.old_process: subprocess.Popen[str] | None = None
            self.new_process: subprocess.Popen[str] | None = None
            self.old_log_handle: TextIO | None = None
            self.new_log_handle: TextIO | None = None
            self.old_session_id = f"{args.run_id}:old"
            self.new_session_id = f"{args.run_id}:new"
            self.armed_seen = False
            self.old_active_seen = False
            self.new_active_seen = False
            self.fallback_seen = False
            self.old_message_created = False
            self.old_message_released = False
            self.old_message_observed = False
            self.old_stop_monotonic_ns: int | None = None
            self.new_active_monotonic_ns: int | None = None
            self.release_monotonic_ns: int | None = None
            self.window_close_monotonic_ns: int | None = None
            self.safety_reason: str | None = None
            self.peak_tilt_rad = 0.0
            self.peak_rate_rad_s = 0.0
            self.clock_samples = 0
            self.exit_code: int | None = None
            self.last_nav_state: int | None = None
            self.nav_transitions: list[dict[str, Any]] = []
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
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
                (VehicleControlMode, "/fmu/out/vehicle_control_mode", self._control_mode),
                (
                    RegisterExtComponentRequest,
                    "/fmu/in/register_ext_component_request",
                    self._registration_request,
                ),
                (RegisterExtComponentReply, "/fmu/out/register_ext_component_reply", self._registration),
                (ModeCompleted, "/fmu/out/mode_completed", self._mode_completed),
            ):
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, qos
                )
            self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)
            self.completion_pub = self.create_publisher(
                ModeCompleted, _versioned_topic("/fmu/in/mode_completed", ModeCompleted), 1
            )
            self.timer = self.create_timer(0.05, self._tick)
            self._event("r1_monitor_started", scenario=args.scenario)
            self._start_component("old")

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
            self._event("r1_state_transition", previous=previous, current=state)

        def _start_component(self, role: str) -> None:
            log_path = args.old_log if role == "old" else args.new_log
            handle = log_path.open("w", encoding="utf-8")
            environment = os.environ.copy()
            environment["UAV_SF_R1_SESSION_ROLE"] = role
            environment["UAV_SF_R1_PRODUCER_SESSION_ID"] = (
                self.old_session_id if role == "old" else self.new_session_id
            )
            environment["UAV_SF_R1_CONTROL_DIR"] = str(args.control_dir)
            process = subprocess.Popen(
                [str(args.mode_bin)],
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
            )
            if role == "old":
                self.old_process = process
                self.old_log_handle = handle
            else:
                self.new_process = process
                self.new_log_handle = handle
            self._event(
                "r1_component_started",
                session_role=role,
                producer_session_id=environment["UAV_SF_R1_PRODUCER_SESSION_ID"],
                pid=process.pid,
            )

        def _stop_component(self, role: str, controlled: bool) -> None:
            process = self.old_process if role == "old" else self.new_process
            if process is None or process.poll() is not None:
                return
            selected_signal = signal.SIGTERM if controlled else signal.SIGKILL
            process.send_signal(selected_signal)
            try:
                process.wait(timeout=8.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3.0)
            if role == "old":
                self.old_stop_monotonic_ns = time.monotonic_ns()
            self._event(
                "r1_component_stopped",
                session_role=role,
                controlled_lifecycle_condition=controlled,
                signal=int(selected_signal),
                returncode=process.returncode,
            )

        def stop_all(self) -> None:
            self._stop_component("new", controlled=True)
            self._stop_component("old", controlled=True)
            for handle_name in ("old_log_handle", "new_log_handle"):
                handle = getattr(self, handle_name)
                if handle is not None and not handle.closed:
                    handle.close()

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
                    self.old_active_seen
                    and self.old_mode_id is not None
                    and self.last_nav_state == self.old_mode_id
                    and nav_state != self.old_mode_id
                ):
                    self.fallback_seen = True
                    self._event(
                        "old_session_fallback_observed",
                        source_mode=self.old_mode_id,
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
                self._safety_stop("unexpected_ground_contact_before_terminal_phase")

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

        def _control_mode(self, message: Any) -> None:
            self.control_mode = message

        def _registration_request(self, message: Any) -> None:
            name = _name(message.name)
            if name == "R1 Session old":
                self.old_registration_request_id = int(message.request_id)
                role = "old"
            elif name == "R1 Session new":
                self.new_registration_request_id = int(message.request_id)
                role = "new"
            else:
                return
            self._event(
                "r1_registration_request_observed",
                session_role=role,
                name=name,
                request_id=int(message.request_id),
                register_mode=bool(message.register_mode),
                register_mode_executor=bool(message.register_mode_executor),
                activate_mode_immediately=bool(message.activate_mode_immediately),
            )

        def _registration(self, message: Any) -> None:
            if not bool(message.success):
                return
            name = _name(message.name)
            if name == "R1 Session old":
                self.old_mode_id = int(message.mode_id)
                self.old_executor_id = int(message.mode_executor_id)
                self.old_registration_reply_request_id = int(message.request_id)
                role = "old"
            elif name == "R1 Session new":
                self.new_mode_id = int(message.mode_id)
                self.new_executor_id = int(message.mode_executor_id)
                self.new_registration_reply_request_id = int(message.request_id)
                role = "new"
            else:
                return
            self._event(
                "r1_registration_observed",
                session_role=role,
                name=name,
                request_id=int(message.request_id),
                mode_id=int(message.mode_id),
                executor_id=int(message.mode_executor_id),
                arming_check_id=int(message.arming_check_id),
            )

        def _mode_completed(self, message: Any) -> None:
            self._event(
                "mode_completed_observed",
                nav_state=int(message.nav_state),
                result=int(message.result),
                selected_old_session_semantic=(
                    self.old_message_released
                    and self.old_mode_id is not None
                    and int(message.nav_state) == self.old_mode_id
                ),
            )
            if (
                self.old_message_released
                and self.old_mode_id is not None
                and int(message.nav_state) == self.old_mode_id
            ):
                self.old_message_observed = True

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

        def _controller_snapshot(self) -> dict[str, bool] | None:
            if self.control_mode is None:
                return None
            return {
                name: bool(getattr(self.control_mode, name, False))
                for name in (
                    "flag_multicopter_position_control_enabled",
                    "flag_control_position_enabled",
                    "flag_control_velocity_enabled",
                    "flag_control_attitude_enabled",
                    "flag_control_rates_enabled",
                    "flag_control_allocation_enabled",
                )
            }

        def _create_old_message(self) -> None:
            assert self.old_mode_id is not None
            self.old_message_created = True
            self._event(
                "old_session_message_held",
                semantic="completion_event",
                message_type="px4_msgs/msg/ModeCompleted",
                nav_state=self.old_mode_id,
                result=int(ModeCompleted.RESULT_SUCCESS),
                producer_session_id=self.old_session_id,
                held_in_owned_test_namespace=True,
            )

        def _release_old_message(self) -> None:
            assert self.old_mode_id is not None
            message = ModeCompleted()
            message.timestamp = 0
            message.nav_state = self.old_mode_id
            message.result = ModeCompleted.RESULT_SUCCESS
            self.completion_pub.publish(message)
            self.old_message_released = True
            self.release_monotonic_ns = time.monotonic_ns()
            self._event(
                "old_session_message_released_once",
                semantic="completion_event",
                message_type="px4_msgs/msg/ModeCompleted",
                nav_state=self.old_mode_id,
                result=int(ModeCompleted.RESULT_SUCCESS),
                producer_session_id=self.old_session_id,
                release_count=1,
            )

        def _safety_stop(self, reason: str) -> None:
            self.safety_reason = reason
            self._event("formal_safety_stop", reason=reason)
            self._transition("CLEANUP")

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            lifecycle_progressed = (args.control_dir / "new_lifecycle_progressed.marker").exists()
            result = {
                "schema_version": "1.0",
                "run_id": args.run_id,
                "scenario": args.scenario,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "selected_semantic": "ModeCompleted" if args.scenario == "C" else None,
                "expected_successor_nav_state": int(VehicleStatus.NAVIGATION_STATE_AUTO_RTL),
                "old_session": {
                    "mode_id": self.old_mode_id,
                    "executor_id": self.old_executor_id,
                    "producer_session_id": self.old_session_id,
                    "registration_request_id": self.old_registration_request_id,
                    "registration_reply_request_id": self.old_registration_reply_request_id,
                    "active_seen": self.old_active_seen,
                    "stop_monotonic_ns": self.old_stop_monotonic_ns,
                },
                "new_session": {
                    "mode_id": self.new_mode_id,
                    "executor_id": self.new_executor_id,
                    "producer_session_id": self.new_session_id,
                    "registration_request_id": self.new_registration_request_id,
                    "registration_reply_request_id": self.new_registration_reply_request_id,
                    "active_seen": self.new_active_seen,
                    "active_monotonic_ns": self.new_active_monotonic_ns,
                    "completion_wait_armed": (
                        args.control_dir / "new_completion_wait_armed.marker"
                    ).exists(),
                },
                "old_session_message": {
                    "created": self.old_message_created,
                    "released_once": self.old_message_released,
                    "relayed_observation": self.old_message_observed,
                    "release_monotonic_ns": self.release_monotonic_ns,
                    "new_lifecycle_progressed": lifecycle_progressed,
                },
                "completion_event": {
                    "created": self.old_message_created,
                    "released_once": self.old_message_released,
                    "release_count": 1 if self.old_message_released else 0,
                    "observed": self.old_message_observed,
                    "release_monotonic_ns": self.release_monotonic_ns,
                    "provenance": "EARLIER_SESSION" if args.scenario == "C" else "NONE",
                    "producer_session_id": self.old_session_id if args.scenario == "C" else None,
                    "wire_fields": ["timestamp", "result", "nav_state"],
                    "wire_instance_or_generation_fields": [],
                    "new_lifecycle_progressed": lifecycle_progressed,
                    "successor_request_observed": (
                        args.control_dir / "new_successor_requested.marker"
                    ).exists(),
                },
                "controller_graph_at_close": self._controller_snapshot(),
                "window_close_monotonic_ns": self.window_close_monotonic_ns,
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
            self._event("r1_monitor_finished", **result)
            self.stop_all()
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
            executor = int(getattr(self.status, "executor_in_charge", 0))

            if self.state == "WAIT_FOR_FMU":
                ready = (
                    self.position is not None
                    and bool(self.position.xy_valid)
                    and self.old_mode_id is not None
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
                    self._transition("ACTIVATE_OLD")
                return
            if self.state == "ACTIVATE_OLD":
                assert self.old_mode_id is not None
                self._periodic(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(self.old_mode_id),
                )
                if nav_state == self.old_mode_id:
                    self.old_active_seen = True
                    self._event(
                        "old_session_active_snapshot",
                        mode_id=nav_state,
                        executor_in_charge=executor,
                        controller_graph=self._controller_snapshot(),
                    )
                    self._transition("STABILIZE_OLD")
                return
            if self.state == "STABILIZE_OLD":
                if nav_state != self.old_mode_id:
                    self._finish("ENVIRONMENT_FAILURE", "old route exited before rollover")
                elif now - self.state_started >= 1.0:
                    if args.scenario == "C":
                        self._create_old_message()
                    self._transition("STOP_OLD")
                return
            if self.state == "STOP_OLD":
                self._stop_component("old", controlled=args.scenario != "B")
                self._transition("WAIT_FALLBACK")
                return
            if self.state == "WAIT_FALLBACK":
                if self.old_mode_id is not None and nav_state != self.old_mode_id:
                    self.fallback_seen = True
                    if now - self.state_started >= 0.5:
                        self._start_component("new")
                        self._transition("WAIT_NEW_REGISTRATION")
                return
            if self.state == "WAIT_NEW_REGISTRATION":
                if self.new_mode_id is not None:
                    self._transition("WAIT_NEW_ACTIVE")
                return
            if self.state == "WAIT_NEW_ACTIVE":
                wait_armed = (args.control_dir / "new_completion_wait_armed.marker").exists()
                if nav_state == self.new_mode_id and executor == self.new_executor_id and wait_armed:
                    self.new_active_seen = True
                    self.new_active_monotonic_ns = time.monotonic_ns()
                    self._event(
                        "new_session_active_snapshot",
                        mode_id=nav_state,
                        executor_in_charge=executor,
                        controller_graph=self._controller_snapshot(),
                        completion_wait_armed=wait_armed,
                    )
                    self._transition("STABILIZE_NEW")
                return
            if self.state == "STABILIZE_NEW":
                if nav_state != self.new_mode_id:
                    self._finish("ENVIRONMENT_FAILURE", "new route exited before isolation window")
                elif now - self.state_started >= 1.0:
                    if args.scenario == "C":
                        self._release_old_message()
                        self._transition("OBSERVE_RELEASE")
                    else:
                        self._transition("OBSERVE_CONTROL")
                return
            if self.state in {"OBSERVE_RELEASE", "OBSERVE_CONTROL"}:
                if now - self.state_started >= 1.5:
                    self.window_close_monotonic_ns = time.monotonic_ns()
                    self._event(
                        "r1_isolation_window_closed",
                        nav_state=nav_state,
                        executor_in_charge=executor,
                        new_lifecycle_progressed=(
                            args.control_dir / "new_lifecycle_progressed.marker"
                        ).exists(),
                        controller_graph=self._controller_snapshot(),
                    )
                    self._transition("CLEANUP")
                return
            if self.state == "CLEANUP":
                self._periodic(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
                if self.armed_seen and not armed:
                    status = "FORMAL_SAFETY_STOP" if self.safety_reason else "PASS"
                    reason = self.safety_reason or "rollover window observed and Land/Disarm complete"
                    self._finish(status, reason)

    rclpy.init()
    node = Monitor()
    try:
        while rclpy.ok() and node.exit_code is None:
            rclpy.spin_once(node, timeout_sec=0.1)
        return node.exit_code if node.exit_code is not None else 1
    finally:
        node.stop_all()
        node.destroy_node()
        rclpy.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--mode-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--old-log", type=Path, required=True)
    parser.add_argument("--new-log", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=150.0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
