from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import rclpy
from px4_msgs.msg import (
    VehicleAttitude,
    VehicleCommand,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleOdometry,
    VehicleStatus,
)
from rclpy.node import Node

from family_a_runtime.common import PX4_QOS, versioned_topic
from scripts.safety.supervisor import SafetyLimits, SafetySupervisor


class ActiveSafetySupervisor(Node):
    def __init__(self) -> None:
        super().__init__("family_a_active_safety_supervisor")
        for name in ("run_id", "sidecar_path", "decision_path", "limits_path"):
            self.declare_parameter(name, "")
        self._run_id = self.get_parameter("run_id").value
        self._sidecar_path = Path(self.get_parameter("sidecar_path").value)
        self._decision_path = Path(self.get_parameter("decision_path").value)
        limits_path = Path(self.get_parameter("limits_path").value)
        if not self._run_id or not limits_path.is_file():
            raise RuntimeError("run_id and a valid limits_path are required")
        limits = json.loads(limits_path.read_text(encoding="utf-8"))["safety"]
        started = time.monotonic_ns()
        self._supervisor = SafetySupervisor(
            SafetyLimits.from_mapping(limits),
            started_ns=started,
            required_collectors={"telemetry_sidecar"},
        )
        self._status: VehicleStatus | None = None
        self._position: VehicleLocalPosition | None = None
        self._attitude: VehicleAttitude | None = None
        self._odometry: VehicleOdometry | None = None
        self._land: VehicleLandDetected | None = None
        self._minimum_z: float | None = None
        self._became_airborne = False
        self._stop_written = False
        self._command_pub = self.create_publisher(
            VehicleCommand, "/fmu/in/vehicle_command", PX4_QOS
        )
        subscriptions = (
            (
                VehicleStatus,
                versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
                "_status",
            ),
            (
                VehicleLocalPosition,
                versioned_topic(
                    "/fmu/out/vehicle_local_position", VehicleLocalPosition
                ),
                "_position",
            ),
            (VehicleAttitude, "/fmu/out/vehicle_attitude", "_attitude"),
            (
                VehicleOdometry,
                versioned_topic("/fmu/out/vehicle_odometry", VehicleOdometry),
                "_odometry",
            ),
            (VehicleLandDetected, "/fmu/out/vehicle_land_detected", "_land"),
        )
        for message_type, topic, attribute in subscriptions:
            self.create_subscription(
                message_type,
                topic,
                lambda message, name=attribute: setattr(self, name, message),
                PX4_QOS,
            )
        self.create_timer(0.05, self._tick)

    def _command_land(self) -> None:
        message = VehicleCommand()
        message.timestamp = self.get_clock().now().nanoseconds // 1000
        message.command = VehicleCommand.VEHICLE_CMD_NAV_LAND
        message.target_system = 1
        message.target_component = 1
        message.source_system = 1
        message.source_component = 192
        message.from_external = True
        self._command_pub.publish(message)

    def _tilt_degrees(self) -> float:
        if self._attitude is None:
            return math.nan
        w, x, y, _ = (float(value) for value in self._attitude.q)
        cosine = max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y)))
        return math.degrees(math.acos(cosine))

    def _write_stop(self, decision: dict[str, str]) -> None:
        if self._stop_written:
            return
        self._decision_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "run_id": self._run_id,
            "timestamp_monotonic_ns": time.monotonic_ns(),
            **decision,
        }
        with self._decision_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._stop_written = True

    def _tick(self) -> None:
        now = time.monotonic_ns()
        decision = self._supervisor.observe({"kind": "supervisor_heartbeat"}, now_ns=now)
        try:
            # File mtimes use CLOCK_REALTIME; comparing one with CLOCK_MONOTONIC
            # can make a healthy sidecar look permanently stale.
            age_ns = max(0, time.time_ns() - self._sidecar_path.stat().st_mtime_ns)
        except FileNotFoundError:
            age_ns = self._supervisor.limits.collector_timeout_ns + 1
        if age_ns <= self._supervisor.limits.collector_timeout_ns:
            decision = self._supervisor.observe(
                {"kind": "collector_heartbeat", "collector": "telemetry_sidecar"},
                now_ns=now,
            )
        telemetry_ready = all(
            value is not None
            for value in (
                self._status,
                self._position,
                self._attitude,
                self._odometry,
                self._land,
            )
        )
        if telemetry_ready:
            assert self._status is not None
            assert self._position is not None
            assert self._odometry is not None
            assert self._land is not None
            current_z = float(self._position.z)
            self._minimum_z = (
                current_z if self._minimum_z is None else min(self._minimum_z, current_z)
            )
            if current_z < -0.5 and not self._land.landed:
                self._became_airborne = True
            angular = [float(value) for value in self._odometry.angular_velocity]
            decision = self._supervisor.observe(
                {
                    "kind": "telemetry",
                    # PX4 local NED z grows towards the ground, so loss is
                    # measured from the highest (most negative) observed z.
                    "altitude_loss_m": max(0.0, current_z - self._minimum_z),
                    "horizontal_speed_m_s": math.hypot(
                        float(self._position.vx), float(self._position.vy)
                    ),
                    "vertical_speed_m_s": float(self._position.vz),
                    "attitude_excursion_deg": self._tilt_degrees(),
                    "body_rate_rad_s": math.sqrt(sum(value * value for value in angular)),
                    "unexpected_ground_contact": bool(
                        self._became_airborne
                        and self._land.ground_contact
                        and self._status.arming_state == VehicleStatus.ARMING_STATE_ARMED
                        and self._status.nav_state != VehicleStatus.NAVIGATION_STATE_AUTO_LAND
                    ),
                },
                now_ns=now,
            )
        time_decision = self._supervisor.check_time(now_ns=now)
        if time_decision["decision"] != "CONTINUE":
            decision = time_decision
        if decision["decision"] != "CONTINUE":
            self._command_land()
            self._write_stop(decision)


def main() -> None:
    rclpy.init()
    node = ActiveSafetySupervisor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
