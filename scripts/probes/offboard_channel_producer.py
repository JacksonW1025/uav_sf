#!/usr/bin/env python3
"""Separate Offboard producer used by deterministic P2 and P3 experiments."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.adapters.offboard_adapter import Px4OffboardAdapter
from scripts.behavior.common_behavior_core import CommonBehaviorCore


def _versioned_topic(base: str, message_type: object) -> str:
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def run(events_path: Path, control_dir: Path, timeout_s: float) -> int:
    try:
        import rclpy
        from px4_msgs.msg import TimesyncStatus, VehicleStatus
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    except ImportError as exc:  # pragma: no cover - requires the ROS environment
        raise SystemExit(f"Family A ROS workspace is required: {exc}") from exc

    control_dir.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    class Producer(Node):
        def __init__(self) -> None:
            super().__init__("phase_a2_offboard_producer")
            self.events = events_path.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.deadline = self.started + timeout_s
            self.status: Any | None = None
            self.timesync: Any | None = None
            self.activated = False
            self.mode_requested = False
            self.last_mode_request = 0.0
            self.exit_requested = False
            self.release_started: float | None = None
            self.exit_code: int | None = None
            self.core = CommonBehaviorCore()
            self.behavior_context = os.environ.get("UAV_SF_BEHAVIOR_CONTEXT", "hover")
            self.core.command_for_context(self.behavior_context, 0.0, 0.0)
            self.adapter = Px4OffboardAdapter(
                self,
                event_sink=lambda event: self._event("adapter_event", adapter_event=event),
            )
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
            self.timer = self.create_timer(0.05, self._tick)
            self._event(
                "offboard_producer_started",
                producer_session_id=self.adapter.contract.producer_session_id,
            )

        def _event(self, event_type: str, **fields: object) -> None:
            record = {
                "event_type": event_type,
                "monotonic_ns": time.monotonic_ns(),
                "ros_time_ns": self.get_clock().now().nanoseconds,
                **fields,
            }
            self.events.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            self.events.flush()

        def _status(self, message: Any) -> None:
            self.status = message
            if int(message.nav_state) == int(VehicleStatus.NAVIGATION_STATE_OFFBOARD):
                self.activated = True

        def _timesync(self, message: Any) -> None:
            self.timesync = message
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

        def request_exit(self, signum: int) -> None:
            if self.exit_requested:
                return
            self.exit_requested = True
            self.release_started = time.monotonic()
            self._event("producer_signal", signal=signal.Signals(signum).name)

        def _finish(self, status: str, reason: str) -> None:
            if self.exit_code is not None:
                return
            self._event(
                "offboard_producer_finished",
                status=status,
                reason=reason,
                producer_session_id=self.adapter.contract.producer_session_id,
            )
            self.events.close()
            self.exit_code = 0 if status == "PASS" else 1
            self.timer.cancel()

        def _tick(self) -> None:
            now = time.monotonic()
            timestamp_us = self.get_clock().now().nanoseconds // 1000
            if now >= self.deadline:
                self._finish("FAIL", "producer timeout")
                return

            if self.exit_requested or (control_dir / "stop").exists():
                self.adapter.release(timestamp_us)
                if self.release_started is None:
                    self.release_started = now
                if now - self.release_started >= 0.35:
                    self._finish("PASS", "graceful release completed")
                return

            heartbeat_enabled = not (control_dir / "heartbeat.off").exists()
            setpoint_enabled = not (control_dir / "setpoint.off").exists()
            active_context = (
                self.behavior_context
                if (control_dir / "context.active").exists()
                else "hover"
            )
            self.adapter.publish_channels(
                self.core.command_for_context(
                    active_context, now - self.started, now - self.started
                ),
                producer_timestamp_us=timestamp_us,
                heartbeat_enabled=heartbeat_enabled,
                setpoint_enabled=setpoint_enabled,
            )

            if (control_dir / "activate").exists() and not self.activated:
                if now - self.last_mode_request >= 0.5:
                    self.last_mode_request = now
                    self.mode_requested = True
                    self.adapter.request_mode(producer_timestamp_us=timestamp_us)

    rclpy.init()
    node = Producer()

    def handle(signum: int, _frame: object) -> None:
        node.request_exit(signum)

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    signal.signal(
        signal.SIGCONT,
        lambda signum, _frame: node._event("producer_signal", signal=signal.Signals(signum).name),
    )
    while rclpy.ok() and node.exit_code is None:
        rclpy.spin_once(node, timeout_sec=0.1)
    result = node.exit_code if node.exit_code is not None else 1
    node.destroy_node()
    rclpy.shutdown()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=150.0)
    args = parser.parse_args()
    return run(args.events, args.control_dir, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
