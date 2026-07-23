#!/usr/bin/env python3
"""Live ROS telemetry bridge for the continuous Family A supervisor."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


def _versioned_topic(base: str, message_type: object) -> str:
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def _append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from px4_msgs.msg import (
            TimesyncStatus,
            VehicleAngularVelocity,
            VehicleAttitude,
            VehicleLandDetected,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
    except ImportError as exc:  # pragma: no cover - container-only
        raise SystemExit(f"locked ROS Jazzy workspace is required: {exc}") from exc

    class Collector(Node):
        def __init__(self) -> None:
            super().__init__(f"family_a_telemetry_{args.safe_id}")
            self.started = time.monotonic()
            self.position: Any | None = None
            self.attitude: Any | None = None
            self.angular_velocity: Any | None = None
            self.status: Any | None = None
            self.landed: bool | None = None
            self.takeoff_seen = False
            self.baseline_altitude_m: float | None = None
            self.land_seen = False
            self.disarm_seen = False
            self.clock_samples = 0
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            for message_type, topic, callback in (
                (
                    VehicleLocalPosition,
                    "/fmu/out/vehicle_local_position",
                    self._position,
                ),
                (VehicleAttitude, "/fmu/out/vehicle_attitude", self._attitude),
                (
                    VehicleAngularVelocity,
                    "/fmu/out/vehicle_angular_velocity",
                    self._angular_velocity,
                ),
                (VehicleStatus, "/fmu/out/vehicle_status", self._status),
                (
                    VehicleLandDetected,
                    "/fmu/out/vehicle_land_detected",
                    self._land,
                ),
                (TimesyncStatus, "/fmu/out/timesync_status", self._clock),
            ):
                self.create_subscription(
                    message_type,
                    _versioned_topic(topic, message_type),
                    callback,
                    qos,
                )
            self.timer = self.create_timer(0.1, self._tick)
            args.ready.parent.mkdir(parents=True, exist_ok=True)
            args.ready.write_text(
                json.dumps(
                    {
                        "status": "COLLECTORS_READY",
                        "collectors": args.collector,
                        "runtime_started": False,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

        def _position(self, message: Any) -> None:
            self.position = message
            if bool(message.z_valid):
                altitude = -float(message.z)
                if altitude >= 1.5:
                    self.takeoff_seen = True
                    if self.baseline_altitude_m is None:
                        self.baseline_altitude_m = altitude

        def _attitude(self, message: Any) -> None:
            self.attitude = message

        def _angular_velocity(self, message: Any) -> None:
            self.angular_velocity = message

        def _status(self, message: Any) -> None:
            self.status = message
            armed = int(message.arming_state) == int(
                VehicleStatus.ARMING_STATE_ARMED
            )
            if self.takeoff_seen and not armed:
                self.disarm_seen = True

        def _land(self, message: Any) -> None:
            self.landed = bool(message.landed)
            if self.takeoff_seen and self.landed:
                self.land_seen = True

        def _clock(self, message: Any) -> None:
            self.clock_samples += 1
            _append(
                args.events,
                {
                    "event_type": "clock_observation",
                    "stalled": False,
                    "timestamp_us": int(message.timestamp),
                    "estimated_offset_us": int(message.estimated_offset),
                    "round_trip_time_us": int(message.round_trip_time),
                    "observed_monotonic": time.monotonic(),
                },
            )

        def _tick(self) -> None:
            now = time.monotonic()
            _append(args.events, {"event_type": "monitor_heartbeat", "at": now})
            for collector in args.collector:
                _append(
                    args.events,
                    {
                        "event_type": "collector_heartbeat",
                        "collector": collector,
                        "at": now,
                    },
                )
            if (
                self.position is not None
                and self.attitude is not None
                and self.angular_velocity is not None
            ):
                position = self.position
                attitude = self.attitude
                angular = self.angular_velocity
                horizontal_speed = math.hypot(float(position.vx), float(position.vy))
                q = [float(item) for item in attitude.q]
                q0 = max(-1.0, min(1.0, abs(q[0])))
                attitude_excursion = math.degrees(2.0 * math.acos(q0))
                rates = [float(item) for item in angular.xyz]
                current_altitude = -float(position.z)
                baseline = self.baseline_altitude_m or current_altitude
                _append(
                    args.events,
                    {
                        "event_type": "observation",
                        "controller_values": [
                            float(position.vx),
                            float(position.vy),
                            float(position.vz),
                        ],
                        "actuator_values": q + rates,
                        "altitude_loss_m": max(0.0, baseline - current_altitude),
                        "horizontal_speed_m_s": horizontal_speed,
                        "vertical_speed_m_s": float(position.vz),
                        "attitude_excursion_deg": attitude_excursion,
                        "body_rate_rad_s": max(abs(value) for value in rates),
                        "unexpected_ground_contact": False,
                        "route_epoch_present": False,
                        "writer_lineage_present": False,
                        "controller_lineage_present": False,
                    },
                )
            if args.stop.exists() or now - self.started > args.timeout:
                _append(
                    args.events,
                    {
                        "event_type": "terminal_state",
                        "landed": self.land_seen,
                        "disarmed": self.disarm_seen,
                    },
                )
                result = {
                    "schema_version": "1.0",
                    "status": "COLLECTION_CLOSED",
                    "land_seen": self.land_seen,
                    "disarm_seen": self.disarm_seen,
                    "clock_samples": self.clock_samples,
                    "timeout": now - self.started > args.timeout,
                }
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                rclpy.shutdown()

    rclpy.init()
    collector = Collector()
    try:
        rclpy.spin(collector)
    finally:
        collector.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--stop", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--collector",
        action="append",
        default=["route", "writer_controller", "clock"],
    )
    parser.add_argument("--timeout", type=float, default=155.0)
    args = parser.parse_args()
    args.safe_id = "".join(
        character if character.isalnum() else "_" for character in args.attempt_id
    )
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
