from __future__ import annotations

import time

import rclpy
from px4_msgs.msg import (
    ModeCompleted,
    TimesyncStatus,
    VehicleAttitude,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleOdometry,
    VehicleStatus,
)
from rclpy.node import Node

from family_a_runtime.common import DurableJsonl, PX4_QOS, versioned_topic


class TelemetrySidecar(Node):
    def __init__(self) -> None:
        super().__init__("family_a_telemetry_sidecar")
        self.declare_parameter("run_id")
        self.declare_parameter("output_path")
        run_id = self.get_parameter("run_id").get_parameter_value().string_value
        output = self.get_parameter("output_path").get_parameter_value().string_value
        if not run_id or not output:
            raise RuntimeError("run_id and output_path parameters are required")
        self._run_id = run_id
        self._output = DurableJsonl(output)
        self._output.append("sidecar_started", run_id=run_id)
        self.create_subscription(
            VehicleStatus,
            versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
            self._vehicle_status,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleLocalPosition,
            versioned_topic("/fmu/out/vehicle_local_position", VehicleLocalPosition),
            self._local_position,
            PX4_QOS,
        )
        self.create_subscription(
            TimesyncStatus, "/fmu/out/timesync_status", self._timesync, PX4_QOS
        )
        self.create_subscription(
            ModeCompleted, "/fmu/out/mode_completed", self._mode_completed, PX4_QOS
        )
        self.create_subscription(
            VehicleLandDetected,
            "/fmu/out/vehicle_land_detected",
            self._land_detected,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleAttitude, "/fmu/out/vehicle_attitude", self._attitude, PX4_QOS
        )
        self.create_subscription(
            VehicleOdometry,
            versioned_topic("/fmu/out/vehicle_odometry", VehicleOdometry),
            self._angular_velocity,
            PX4_QOS,
        )
        self.create_timer(0.1, self._heartbeat)

    def _append(self, kind: str, message: object, **payload: object) -> None:
        callback_monotonic_ns = time.monotonic_ns()
        callback_realtime_ns = time.time_ns()
        message_timestamp_us = int(getattr(message, "timestamp"))
        payload.setdefault("received_monotonic_ns", callback_monotonic_ns)
        payload.setdefault("received_realtime_ns", callback_realtime_ns)
        self._output.append(
            kind,
            run_id=self._run_id,
            px4_timestamp_us=message_timestamp_us,
            **payload,
        )

    def _vehicle_status(self, message: VehicleStatus) -> None:
        self._append(
            "vehicle_status",
            message,
            nav_state=int(message.nav_state),
            nav_state_user_intention=int(message.nav_state_user_intention),
            executor_in_charge=int(message.executor_in_charge),
            arming_state=int(message.arming_state),
            failsafe=bool(message.failsafe),
        )

    def _local_position(self, message: VehicleLocalPosition) -> None:
        self._append(
            "vehicle_local_position",
            message,
            x=float(message.x),
            y=float(message.y),
            z=float(message.z),
            vx=float(message.vx),
            vy=float(message.vy),
            vz=float(message.vz),
            xy_valid=bool(message.xy_valid),
            z_valid=bool(message.z_valid),
        )

    def _timesync(self, message: TimesyncStatus) -> None:
        # PX4 rewrites outgoing DDS timestamps into the synchronized absolute
        # domain. The reported offset maps that value back to PX4 boot time,
        # which is the time domain retained by ULog.
        # The raw TimesyncStatus contract is:
        #   PX4 boot = remote realtime + observed offset.
        # PX4 separately rewrites ordinary outgoing timestamp fields with the
        # filtered estimated offset; using that filtered value here would add
        # a systematic, time-varying cross-domain bias.
        boot_us = int(message.remote_timestamp) + int(message.observed_offset)
        callback_monotonic_ns = time.monotonic_ns()
        callback_realtime_ns = time.time_ns()
        self._append(
            "timesync_sample",
            message,
            received_monotonic_ns=callback_monotonic_ns,
            received_realtime_ns=callback_realtime_ns,
            source_domain="px4_boot_us",
            source_us=boot_us,
            # PX4's DDS timestamp is in the synchronized realtime domain.
            # Projecting it with a same-callback realtime/monotonic pair
            # removes ROS callback latency from the bridge fit.
            analysis_projection_ns=(
                int(message.remote_timestamp) * 1000
                + callback_monotonic_ns
                - callback_realtime_ns
            ),
            remote_us=int(message.remote_timestamp),
            observed_offset_us=int(message.observed_offset),
            estimated_offset_us=int(message.estimated_offset),
            round_trip_us=int(message.round_trip_time),
        )

    def _land_detected(self, message: VehicleLandDetected) -> None:
        self._append(
            "vehicle_land_detected",
            message,
            ground_contact=bool(message.ground_contact),
            landed=bool(message.landed),
            at_rest=bool(message.at_rest),
        )

    def _mode_completed(self, message: ModeCompleted) -> None:
        self._append(
            "mode_completed",
            message,
            nav_state=int(message.nav_state),
            result=int(message.result),
        )

    def _attitude(self, message: VehicleAttitude) -> None:
        self._append("vehicle_attitude", message, q=[float(value) for value in message.q])

    def _angular_velocity(self, message: VehicleOdometry) -> None:
        self._append(
            "vehicle_angular_velocity",
            message,
            xyz=[float(value) for value in message.angular_velocity],
        )

    def _heartbeat(self) -> None:
        self._output.append("sidecar_heartbeat", run_id=self._run_id)

    def destroy_node(self) -> bool:
        self._output.append("sidecar_stopped", run_id=self._run_id)
        self._output.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = TelemetrySidecar()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
