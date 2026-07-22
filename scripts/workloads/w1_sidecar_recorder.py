#!/usr/bin/env python3
"""Record observation-only ROS 2 and PX4 evidence for one bounded W1 run."""

from __future__ import annotations

import argparse
import json
import math
import signal
import time
from pathlib import Path
from typing import Any


def _versioned_topic(base: str, message_type: object) -> str:
    version = int(getattr(message_type, "MESSAGE_VERSION", 0))
    return f"{base}_v{version}" if version else base


def _safe_number(value: Any) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _vector(value: Any) -> list[float | None]:
    return [_safe_number(item) for item in value]


def run(args: argparse.Namespace) -> int:
    try:
        import rclpy
        from as2_msgs.msg import AlertEvent, ControllerInfo, PlatformInfo
        from geometry_msgs.msg import PoseStamped, TwistStamped
        from px4_msgs.msg import (
            OffboardControlMode,
            TimesyncStatus,
            TrajectorySetpoint,
            VehicleAngularVelocity,
            VehicleAttitude,
            VehicleCommand,
            VehicleLandDetected,
            VehicleLocalPosition,
            VehicleStatus,
        )
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from rosgraph_msgs.msg import Clock
    except ImportError as exc:  # pragma: no cover - locked ROS runtime only
        raise SystemExit(f"locked W1 ROS workspaces are required: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)

    class Recorder(Node):
        def __init__(self) -> None:
            super().__init__(f"w1_{args.run_id.replace('-', '_')}_sidecar")
            self.handle = args.output.open("w", encoding="utf-8")
            self.started = time.monotonic()
            self.last_nav_state: int | None = None
            self.timesync: Any | None = None
            self.counts: dict[str, int] = {}
            self.publisher_graph_recorded = False
            self.stop_requested = False
            best_effort = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=50,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            reliable = QoSProfile(depth=50)
            subscriptions = (
                (VehicleStatus, "/fmu/out/vehicle_status", self._status, best_effort),
                (VehicleLandDetected, "/fmu/out/vehicle_land_detected", self._land, best_effort),
                (VehicleLocalPosition, "/fmu/out/vehicle_local_position", self._position, best_effort),
                (VehicleAttitude, "/fmu/out/vehicle_attitude", self._attitude, best_effort),
                (
                    VehicleAngularVelocity,
                    "/fmu/out/vehicle_angular_velocity",
                    self._angular_velocity,
                    best_effort,
                ),
                (TimesyncStatus, "/fmu/out/timesync_status", self._timesync, best_effort),
                (TrajectorySetpoint, "/fmu/in/trajectory_setpoint", self._trajectory, best_effort),
                (OffboardControlMode, "/fmu/in/offboard_control_mode", self._offboard, best_effort),
                (VehicleCommand, "/fmu/in/vehicle_command", self._vehicle_command, reliable),
                (PlatformInfo, "/drone0/platform/info", self._platform, reliable),
                (ControllerInfo, "/drone0/controller/info", self._controller, reliable),
                (AlertEvent, "/drone0/alert_event", self._alert, reliable),
                (PoseStamped, "/drone0/motion_reference/pose", self._motion_pose, best_effort),
                (TwistStamped, "/drone0/motion_reference/twist", self._motion_twist, best_effort),
                (Clock, "/clock", self._clock, best_effort),
            )
            for message_type, topic, callback, qos in subscriptions:
                self.create_subscription(
                    message_type, _versioned_topic(topic, message_type), callback, qos
                )
            self.timer = self.create_timer(1.0, self._graph)
            self._event(
                "sidecar_started",
                observation_only=True,
                command_publishers_created=0,
                run_id=args.run_id,
            )

        def _event(self, event_type: str, **fields: Any) -> None:
            self.counts[event_type] = self.counts.get(event_type, 0) + 1
            record = {
                "event_type": event_type,
                "monotonic_ns": time.monotonic_ns(),
                "ros_time_ns": self.get_clock().now().nanoseconds,
                **fields,
            }
            self.handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            self.handle.flush()

        def _status(self, msg: Any) -> None:
            current = int(msg.nav_state)
            if current != self.last_nav_state:
                self._event(
                    "nav_state_transition",
                    previous=self.last_nav_state,
                    current=current,
                    arming_state=int(msg.arming_state),
                    failsafe=bool(msg.failsafe),
                    topic="/fmu/out/vehicle_status",
                    topic_type="px4_msgs/msg/VehicleStatus",
                    qos="BEST_EFFORT_VOLATILE_KEEP_LAST_50",
                    px4_timestamp_us=int(msg.timestamp),
                )
                self.last_nav_state = current

        def _land(self, msg: Any) -> None:
            self._event(
                "land_state",
                landed=bool(msg.landed),
                ground_contact=bool(msg.ground_contact),
                maybe_landed=bool(msg.maybe_landed),
                px4_timestamp_us=int(msg.timestamp),
            )

        def _position(self, msg: Any) -> None:
            self._event(
                "physical_state",
                topic="/fmu/out/vehicle_local_position",
                topic_type="px4_msgs/msg/VehicleLocalPosition",
                qos="BEST_EFFORT_VOLATILE_KEEP_LAST_50",
                px4_timestamp_us=int(msg.timestamp),
                values={
                    "position_ned_m": [_safe_number(msg.x), _safe_number(msg.y), _safe_number(msg.z)],
                    "velocity_ned_m_s": [_safe_number(msg.vx), _safe_number(msg.vy), _safe_number(msg.vz)],
                    "xy_valid": bool(msg.xy_valid),
                    "z_valid": bool(msg.z_valid),
                },
            )
            self._clock_sample(int(msg.timestamp), "vehicle_local_position")

        def _attitude(self, msg: Any) -> None:
            self._event(
                "physical_attitude",
                px4_timestamp_us=int(msg.timestamp),
                values={"quaternion_wxyz": _vector(msg.q)},
            )

        def _angular_velocity(self, msg: Any) -> None:
            self._event(
                "physical_angular_velocity",
                px4_timestamp_us=int(msg.timestamp),
                values={"xyz_rad_s": _vector(msg.xyz)},
            )

        def _timesync(self, msg: Any) -> None:
            self.timesync = msg
            self._clock_sample(int(msg.timestamp), "timesync_status")

        def _clock_sample(self, outbound_us: int, source: str) -> None:
            if self.timesync is None:
                return
            self._event(
                "clock_bridge_sample",
                sample_source=source,
                px4_outbound_timestamp_us=outbound_us,
                px4_boot_timestamp_us=outbound_us + int(self.timesync.estimated_offset),
                ros_receive_ns=self.get_clock().now().nanoseconds,
                monotonic_receive_ns=time.monotonic_ns(),
                timesync_source_protocol=int(self.timesync.source_protocol),
                timesync_estimated_offset_us=int(self.timesync.estimated_offset),
                timesync_round_trip_time_us=int(self.timesync.round_trip_time),
                timesync_converged=int(self.timesync.source_protocol) == 2,
            )

        def _trajectory(self, msg: Any) -> None:
            self._event(
                "setpoint_sample",
                topic="/fmu/in/trajectory_setpoint",
                topic_type="px4_msgs/msg/TrajectorySetpoint",
                qos="BEST_EFFORT_VOLATILE_KEEP_LAST_50",
                subject_timestamp_us=int(msg.timestamp),
                producer_identity="/drone0/platform",
                producer_session=args.run_id,
                values={
                    "position_ned_m": _vector(msg.position),
                    "velocity_ned_m_s": _vector(msg.velocity),
                    "acceleration_ned_m_s2": _vector(msg.acceleration),
                    "yaw_rad": _safe_number(msg.yaw),
                    "yaw_rate_rad_s": _safe_number(msg.yawspeed),
                },
            )

        def _offboard(self, msg: Any) -> None:
            active = [
                name
                for name in ("position", "velocity", "acceleration", "attitude", "body_rate", "thrust_and_torque", "direct_actuator")
                if bool(getattr(msg, name))
            ]
            self._event(
                "offboard_control_mode",
                subject_timestamp_us=int(msg.timestamp),
                active_levels=active,
            )

        def _vehicle_command(self, msg: Any) -> None:
            self._event(
                "observed_vehicle_command",
                command=int(msg.command),
                px4_timestamp_us=int(msg.timestamp),
                source_system=int(msg.source_system),
                source_component=int(msg.source_component),
            )

        def _platform(self, msg: Any) -> None:
            self._event(
                "platform_info",
                topic="/drone0/platform/info",
                topic_type="as2_msgs/msg/PlatformInfo",
                qos="RELIABLE_VOLATILE_KEEP_LAST_50",
                connected=bool(msg.connected),
                armed=bool(msg.armed),
                offboard=bool(msg.offboard),
                platform_state=int(msg.status.state),
                control_mode=int(msg.current_control_mode.control_mode),
                yaw_mode=int(msg.current_control_mode.yaw_mode),
            )

        def _controller(self, msg: Any) -> None:
            self._event(
                "controller_info",
                topic="/drone0/controller/info",
                topic_type="as2_msgs/msg/ControllerInfo",
                qos="RELIABLE_VOLATILE_KEEP_LAST_50",
                controller_identity="/drone0/controller_manager:pid_speed_controller",
                input_control_mode=int(msg.input_control_mode.control_mode),
                output_control_mode=int(msg.output_control_mode.control_mode),
            )

        def _alert(self, msg: Any) -> None:
            self._event("alert_event", alert=int(msg.alert), description=str(msg.description))

        def _motion_pose(self, msg: Any) -> None:
            self._event(
                "motion_reference",
                topic="/drone0/motion_reference/pose",
                topic_type="geometry_msgs/msg/PoseStamped",
                qos="BEST_EFFORT_VOLATILE_KEEP_LAST_50",
                values={
                    "position_enu_m": [
                        _safe_number(msg.pose.position.x),
                        _safe_number(msg.pose.position.y),
                        _safe_number(msg.pose.position.z),
                    ],
                    "orientation_xyzw": [
                        _safe_number(msg.pose.orientation.x),
                        _safe_number(msg.pose.orientation.y),
                        _safe_number(msg.pose.orientation.z),
                        _safe_number(msg.pose.orientation.w),
                    ],
                },
            )

        def _motion_twist(self, msg: Any) -> None:
            self._event(
                "motion_reference",
                topic="/drone0/motion_reference/twist",
                topic_type="geometry_msgs/msg/TwistStamped",
                qos="BEST_EFFORT_VOLATILE_KEEP_LAST_50",
                values={
                    "linear_enu_m_s": [
                        _safe_number(msg.twist.linear.x),
                        _safe_number(msg.twist.linear.y),
                        _safe_number(msg.twist.linear.z),
                    ],
                    "angular_flu_rad_s": [
                        _safe_number(msg.twist.angular.x),
                        _safe_number(msg.twist.angular.y),
                        _safe_number(msg.twist.angular.z),
                    ],
                },
            )

        def _clock(self, msg: Any) -> None:
            self._event(
                "ros_clock",
                clock_ns=int(msg.clock.sec) * 1_000_000_000 + int(msg.clock.nanosec),
            )

        def _graph(self) -> None:
            if self.publisher_graph_recorded:
                return
            topics = (
                "/drone0/motion_reference/pose",
                "/drone0/motion_reference/twist",
                "/fmu/in/trajectory_setpoint",
            )
            graph: dict[str, list[dict[str, str]]] = {}
            for topic in topics:
                infos = self.get_publishers_info_by_topic(topic)
                if not infos:
                    return
                graph[topic] = [
                    {
                        "node_name": info.node_name,
                        "node_namespace": info.node_namespace,
                        "topic_type": info.topic_type,
                        "endpoint_gid": bytes(info.endpoint_gid).hex(),
                    }
                    for info in infos
                ]
            self.publisher_graph_recorded = True
            self._event("publisher_graph", publishers=graph)

        def close(self) -> None:
            self._event(
                "sidecar_finished",
                duration_s=round(time.monotonic() - self.started, 3),
                event_counts=self.counts,
                observation_only=True,
                command_publications=0,
            )
            self.handle.close()

    rclpy.init()
    node = Recorder()

    def request_stop(_signum: int, _frame: object) -> None:
        node.stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    while rclpy.ok() and not node.stop_requested:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.close()
    node.destroy_node()
    rclpy.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
