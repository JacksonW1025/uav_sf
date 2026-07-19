#!/usr/bin/env python3
"""Collect lifecycle evidence for an External Mode completion successor chain."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _versioned_topic(base: str, message_type: object) -> str:
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def run(
    run_id: str,
    output: Path,
    events_path: Path,
    timeout_s: float,
    post_disarm_capture_s: float,
    component_name: str,
) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            ModeCompleted,
            RegisterExtComponentReply,
            TimesyncStatus,
            VehicleCommand,
            VehicleLandDetected,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover - requires the ROS environment
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__(f"successor_lifecycle_{run_id}")
            self.output = output
            self.events_path = events_path
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.events = self.events_path.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + timeout_s
            self.finish_not_before: float | None = None
            self.exit_code: int | None = None
            self.status_message: Any | None = None
            self.landed: bool | None = None
            self.registered_mode_id: int | None = None
            self.registered_executor_id: int | None = None
            self.owned_mode: int | None = None
            self.armed_seen = False
            self.external_active_seen = False
            self.land_selected_seen = False
            self.landed_seen = False
            self.disarmed_seen = False
            self.last_status: tuple[int, int, int, int, bool] | None = None
            self.last_landed: bool | None = None

            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            reliable_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self.create_subscription(
                VehicleStatus,
                _versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
                self._status,
                qos,
            )
            self.create_subscription(
                VehicleLandDetected,
                _versioned_topic("/fmu/out/vehicle_land_detected", VehicleLandDetected),
                self._land_detected,
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
            self.create_subscription(
                ModeCompleted,
                _versioned_topic("/fmu/out/mode_completed", ModeCompleted),
                self._mode_completed,
                qos,
            )
            self.create_subscription(
                VehicleCommand,
                _versioned_topic(
                    "/fmu/in/vehicle_command_mode_executor", VehicleCommand
                ),
                self._executor_command,
                reliable_qos,
            )
            self.create_subscription(
                TimesyncStatus,
                _versioned_topic("/fmu/out/timesync_status", TimesyncStatus),
                self._timesync,
                qos,
            )
            self.timer = self.create_timer(0.05, self._tick)
            self._event("monitor_started", details={"component_name": component_name})

        def _snapshot(self) -> dict[str, object]:
            status = self.status_message
            armed = None
            if status is not None:
                armed = int(status.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)
            return {
                "schema_version": "1.0",
                "run_id": run_id,
                "active_mode": int(status.nav_state) if status is not None else None,
                "nav_state_user_intention": (
                    int(status.nav_state_user_intention) if status is not None else None
                ),
                "executor_in_charge": (
                    int(status.executor_in_charge) if status is not None else None
                ),
                "arming_state": int(status.arming_state) if status is not None else None,
                "armed": armed,
                "landed": self.landed,
                "failsafe": bool(status.failsafe) if status is not None else None,
                "registered_mode_id": self.registered_mode_id,
                "registered_executor_id": self.registered_executor_id,
                "owned_mode": self.owned_mode,
            }

        def _event(
            self,
            event_type: str,
            *,
            px4_timestamp_us: int | None = None,
            details: dict[str, object] | None = None,
            clock_fields: dict[str, object] | None = None,
        ) -> None:
            now_ros_ns = self.get_clock().now().nanoseconds
            now_monotonic_ns = time.monotonic_ns()
            record = {
                **self._snapshot(),
                "event_type": event_type,
                "ros_time_ns": now_ros_ns,
                "monotonic_ns": now_monotonic_ns,
                "px4_timestamp_us": px4_timestamp_us,
                "details": details or {},
            }
            if clock_fields:
                record.update(clock_fields)
            self.events.write(json.dumps(record, sort_keys=True) + "\n")
            self.events.flush()

        def _status(self, message: Any) -> None:
            self.status_message = message
            armed = int(message.arming_state) == int(VehicleStatus.ARMING_STATE_ARMED)
            if armed:
                self.armed_seen = True
            if (
                self.registered_mode_id is not None
                and int(message.nav_state) == self.registered_mode_id
            ):
                self.external_active_seen = True
            if int(message.nav_state) == int(VehicleStatus.NAVIGATION_STATE_AUTO_LAND):
                self.land_selected_seen = True
            if self.armed_seen and not armed:
                self.disarmed_seen = True
            current = (
                int(message.nav_state),
                int(message.nav_state_user_intention),
                int(message.executor_in_charge),
                int(message.arming_state),
                bool(message.failsafe),
            )
            if current != self.last_status:
                self.last_status = current
                self._event(
                    "vehicle_status_observed",
                    px4_timestamp_us=int(message.timestamp),
                    details={
                        "nav_state": current[0],
                        "nav_state_user_intention": current[1],
                        "executor_in_charge": current[2],
                        "arming_state": current[3],
                        "failsafe": current[4],
                    },
                )

        def _land_detected(self, message: Any) -> None:
            self.landed = bool(message.landed)
            if self.landed and self.armed_seen:
                self.landed_seen = True
            if self.landed != self.last_landed:
                self.last_landed = self.landed
                self._event(
                    "land_detected_observed",
                    px4_timestamp_us=int(message.timestamp),
                    details={
                        "landed": bool(message.landed),
                        "ground_contact": bool(message.ground_contact),
                        "maybe_landed": bool(message.maybe_landed),
                    },
                )

        def _registration(self, message: Any) -> None:
            name_value = message.name
            if isinstance(name_value, str):
                name = name_value.rstrip("\x00")
            else:
                name = bytes(int(item) for item in name_value).split(b"\0", 1)[0].decode(
                    "utf-8", errors="replace"
                )
            if not bool(message.success) or name != component_name:
                return
            self.registered_mode_id = int(message.mode_id)
            self.registered_executor_id = int(message.mode_executor_id)
            self.owned_mode = self.registered_mode_id
            self._event(
                "registration_observed",
                px4_timestamp_us=int(message.timestamp),
                details={
                    "name": name,
                    "success": True,
                    "mode_id": self.registered_mode_id,
                    "mode_executor_id": self.registered_executor_id,
                    "arming_check_id": int(message.arming_check_id),
                },
            )

        def _mode_completed(self, message: Any) -> None:
            self._event(
                "mode_completed_observed",
                px4_timestamp_us=int(message.timestamp),
                details={"nav_state": int(message.nav_state), "result": int(message.result)},
            )

        def _executor_command(self, message: Any) -> None:
            self._event(
                "executor_command_observed",
                px4_timestamp_us=None,
                details={
                    "message_timestamp": int(message.timestamp),
                    "command": int(message.command),
                    "source_system": int(message.source_system),
                    "source_component": int(message.source_component),
                    "target_system": int(message.target_system),
                    "target_component": int(message.target_component),
                },
            )

        def _timesync(self, message: Any) -> None:
            receive_ros_ns = self.get_clock().now().nanoseconds
            receive_monotonic_ns = time.monotonic_ns()
            outbound_us = int(message.timestamp)
            offset_us = int(message.estimated_offset)
            self._event(
                "clock_bridge_sample",
                px4_timestamp_us=outbound_us + offset_us,
                details={"sample_source": "timesync_status"},
                clock_fields={
                    "px4_outbound_timestamp_us": outbound_us,
                    "px4_boot_timestamp_us": outbound_us + offset_us,
                    "ros_receive_ns": receive_ros_ns,
                    "monotonic_receive_ns": receive_monotonic_ns,
                    "timesync_source_protocol": int(message.source_protocol),
                    "timesync_estimated_offset_us": offset_us,
                    "timesync_round_trip_time_us": int(message.round_trip_time),
                    "timesync_converged": int(message.source_protocol) == 2,
                },
            )

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            result = {
                "schema_version": "1.0",
                "run_id": run_id,
                "status": status,
                "reason": reason,
                "duration_s": round(time.monotonic() - self.started, 3),
                "registered_mode_id": self.registered_mode_id,
                "registered_executor_id": self.registered_executor_id,
                "armed_seen": self.armed_seen,
                "external_active_seen": self.external_active_seen,
                "land_selected_seen": self.land_selected_seen,
                "landed_seen": self.landed_seen,
                "disarmed_seen": self.disarmed_seen,
            }
            self._event("monitor_finished", details=result)
            self.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            self.events.close()
            self.exit_code = 0 if status == "PASS" else 1
            self.timer.cancel()

        def _tick(self) -> None:
            now = time.monotonic()
            if now >= self.deadline:
                self._finish("FAIL", "lifecycle monitor timeout")
                return
            terminal = (
                self.armed_seen
                and self.external_active_seen
                and self.land_selected_seen
                and self.landed_seen
                and self.disarmed_seen
            )
            if terminal and self.finish_not_before is None:
                self.finish_not_before = now + post_disarm_capture_s
            if self.finish_not_before is not None and now >= self.finish_not_before:
                self._finish("PASS", "external completion to Land and Disarm observed")

    rclpy.init()
    node = Monitor()
    while rclpy.ok() and node.exit_code is None:
        rclpy.spin_once(node, timeout_sec=0.2)
    exit_code = node.exit_code if node.exit_code is not None else 1
    node.destroy_node()
    rclpy.shutdown()
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--post-disarm-capture", type=float, default=2.0)
    parser.add_argument("--component-name", default="Successor Baseline")
    args = parser.parse_args()
    return run(
        args.run_id,
        args.output,
        args.events,
        args.timeout,
        args.post_disarm_capture,
        args.component_name,
    )


if __name__ == "__main__":
    raise SystemExit(main())
