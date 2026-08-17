from __future__ import annotations

import math
import time

import rclpy
from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleAttitudeSetpoint,
    VehicleCommand,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleRatesSetpoint,
    VehicleStatus,
)
from rclpy.node import Node

from family_a_runtime.common import DurableJsonl, PX4_QOS, versioned_topic
from scripts.runtime.physical_readiness import PhysicalTakeoffGate
from scripts.runtime.moving_workload import progress_from_origin, straight_line_target


class OffboardController(Node):
    def __init__(self) -> None:
        super().__init__("family_a_offboard_controller")
        defaults = {
            "run_id": "",
            "lifecycle_path": "",
            "setpoint_kind": "trajectory",
            "fault_mode": "normal",
            "source_route": "px4_internal",
            "successor_route": "internal_land",
            "prestream_s": 1.0,
            "active_s": 8.0,
            "stall_after_s": 3.0,
            "hover_altitude_m": 3.0,
            "successor_dwell_s": 2.0,
            "repeat_count": 1,
            "source_dwell_s": 1.0,
            "target_system": 1,
            "airborne_minimum_height_m": 0.5,
            "airborne_dwell_s": 0.5,
            "workload_profile": "hover",
            "motion_settle_s": 1.0,
            "motion_speed_m_s": 0.75,
            "motion_distance_m": 3.5,
            "motion_entry_progress_m": 0.75,
            "motion_completion_progress_m": 2.5,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self._run_id = self.get_parameter("run_id").value
        lifecycle_path = self.get_parameter("lifecycle_path").value
        self._setpoint_kind = self.get_parameter("setpoint_kind").value
        self._fault_mode = self.get_parameter("fault_mode").value
        self._source_route = self.get_parameter("source_route").value
        self._successor_route = self.get_parameter("successor_route").value
        self._prestream_s = float(self.get_parameter("prestream_s").value)
        self._active_s = float(self.get_parameter("active_s").value)
        self._stall_after_s = float(self.get_parameter("stall_after_s").value)
        self._altitude = float(self.get_parameter("hover_altitude_m").value)
        self._successor_dwell_s = float(
            self.get_parameter("successor_dwell_s").value
        )
        self._repeat_count = int(self.get_parameter("repeat_count").value)
        self._source_dwell_ns = int(
            float(self.get_parameter("source_dwell_s").value) * 1_000_000_000
        )
        self._target_system = int(self.get_parameter("target_system").value)
        self._workload_profile = self.get_parameter("workload_profile").value
        self._motion_settle_s = float(self.get_parameter("motion_settle_s").value)
        self._motion_speed_m_s = float(self.get_parameter("motion_speed_m_s").value)
        self._motion_distance_m = float(self.get_parameter("motion_distance_m").value)
        self._motion_entry_progress_m = float(self.get_parameter("motion_entry_progress_m").value)
        self._motion_completion_progress_m = float(self.get_parameter("motion_completion_progress_m").value)
        self._takeoff_gate = PhysicalTakeoffGate(
            minimum_height_m=float(
                self.get_parameter("airborne_minimum_height_m").value
            ),
            dwell_s=float(self.get_parameter("airborne_dwell_s").value),
        )
        if not self._run_id or not lifecycle_path:
            raise RuntimeError("run_id and lifecycle_path are required")
        if self._setpoint_kind not in {"trajectory", "attitude", "body_rate"}:
            raise RuntimeError("unsupported setpoint_kind")
        if self._fault_mode not in {"normal", "process_exit", "setpoint_stall"}:
            raise RuntimeError("unsupported fault_mode")
        if self._source_route not in {"px4_internal", "internal_hold", "internal_rtl"}:
            raise RuntimeError("unsupported source_route")
        if self._successor_route not in {"internal_hold", "internal_rtl", "internal_land"}:
            raise RuntimeError("unsupported successor_route")
        if self._repeat_count < 1:
            raise RuntimeError("repeat_count must be positive")
        if self._source_dwell_ns < 0:
            raise RuntimeError("source_dwell_s must be non-negative")
        if not 1 <= self._target_system <= 255:
            raise RuntimeError("target_system must be in [1, 255]")
        if self._workload_profile not in {"hover", "straight_line"}:
            raise RuntimeError("unsupported workload_profile")
        if self._repeat_count > 1 and self._successor_route == "internal_land":
            raise RuntimeError("re-entry requires Hold or RTL as the intermediate successor")
        self._log = DurableJsonl(lifecycle_path)
        self._started_ns = time.monotonic_ns()
        self._commanded = False
        self._takeoff_sent = False
        self._takeoff_sent_ns: int | None = None
        self._source_setup_commanded = False
        self._source_setup_sent_ns: int | None = None
        self._arm_sent_ns: int | None = None
        self._airborne_ns: int | None = None
        self._landing_commanded = False
        self._released = False
        self._fault_logged = False
        self._cycle = 0
        self._activation_ns: int | None = None
        self._successor_observed_ns: int | None = None
        self._first_command_logged = False
        self._source_ready_ns: int | None = None
        self._status: VehicleStatus | None = None
        self._land: VehicleLandDetected | None = None
        self._ever_armed = False
        self._ever_offboard = False
        self._ever_airborne = False
        self._latest_x_m: float | None = None
        self._motion_origin_x_m: float | None = None
        self._motion_entered = False
        self._motion_completed = False
        self._control_pub = self.create_publisher(
            OffboardControlMode, "/fmu/in/offboard_control_mode", PX4_QOS
        )
        self._trajectory_pub = self.create_publisher(
            TrajectorySetpoint, "/fmu/in/trajectory_setpoint", PX4_QOS
        )
        self._attitude_pub = self.create_publisher(
            VehicleAttitudeSetpoint,
            versioned_topic("/fmu/in/vehicle_attitude_setpoint", VehicleAttitudeSetpoint),
            PX4_QOS,
        )
        self._rates_pub = self.create_publisher(
            VehicleRatesSetpoint, "/fmu/in/vehicle_rates_setpoint", PX4_QOS
        )
        self._command_pub = self.create_publisher(
            VehicleCommand, "/fmu/in/vehicle_command", PX4_QOS
        )
        self.create_subscription(
            VehicleStatus,
            versioned_topic("/fmu/out/vehicle_status", VehicleStatus),
            self._status_callback,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleLandDetected,
            "/fmu/out/vehicle_land_detected",
            self._land_callback,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleLocalPosition,
            versioned_topic("/fmu/out/vehicle_local_position", VehicleLocalPosition),
            self._local_position_callback,
            PX4_QOS,
        )
        self.create_timer(0.05, self._tick)
        self._log.append(
            "producer_started",
            run_id=self._run_id,
            producer_session=f"offboard-{self._run_id}",
            setpoint_kind=self._setpoint_kind,
            fault_mode=self._fault_mode,
        )

    def _status_callback(self, message: VehicleStatus) -> None:
        self._status = message
        if message.arming_state == VehicleStatus.ARMING_STATE_ARMED:
            self._ever_armed = True
        if message.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD:
            self._ever_offboard = True
            if self._activation_ns is None:
                self._activation_ns = time.monotonic_ns()
                self._log.append(
                    "offboard_observed_active",
                    run_id=self._run_id,
                    cycle=self._cycle,
                )
        expected_successor = {
            "internal_hold": VehicleStatus.NAVIGATION_STATE_AUTO_LOITER,
            "internal_rtl": VehicleStatus.NAVIGATION_STATE_AUTO_RTL,
            "internal_land": VehicleStatus.NAVIGATION_STATE_AUTO_LAND,
        }[self._successor_route]
        if self._released and message.nav_state == expected_successor:
            if self._successor_observed_ns is None:
                self._successor_observed_ns = time.monotonic_ns()
                self._log.append(
                    "successor_observed_active",
                    run_id=self._run_id,
                    route=self._successor_route,
                    cycle=self._cycle,
                )

    def _land_callback(self, message: VehicleLandDetected) -> None:
        self._land = message
        self._takeoff_gate.observe_land(
            landed=bool(message.landed), now_ns=time.monotonic_ns()
        )
        self._update_physical_takeoff_state()

    def _local_position_callback(self, message: VehicleLocalPosition) -> None:
        self._latest_x_m = float(message.x) if bool(message.xy_valid) else None
        self._takeoff_gate.observe_local_position(
            z_m=float(message.z),
            z_valid=bool(message.z_valid),
            now_ns=time.monotonic_ns(),
        )
        self._update_physical_takeoff_state()
        self._update_motion_state()

    def _update_motion_state(self) -> None:
        if self._workload_profile != "straight_line" or self._activation_ns is None or self._latest_x_m is None:
            return
        if self._motion_origin_x_m is None:
            self._motion_origin_x_m = self._latest_x_m
        progress = progress_from_origin(self._latest_x_m, self._motion_origin_x_m)
        if not self._motion_entered and progress >= self._motion_entry_progress_m:
            self._motion_entered = True
            self._log.append("motion_phase_entered", run_id=self._run_id, along_track_progress_m=progress)
        if not self._motion_completed and progress >= self._motion_completion_progress_m:
            self._motion_completed = True
            self._log.append("motion_phase_completed", run_id=self._run_id, along_track_progress_m=progress)

    def _update_physical_takeoff_state(self) -> None:
        if self._ever_airborne or not self._takeoff_gate.evaluate(time.monotonic_ns()):
            return
        self._ever_airborne = True
        self._airborne_ns = self._takeoff_gate.ready_ns
        self._log.append(
            "physical_takeoff_ready",
            run_id=self._run_id,
            minimum_height_m=self._takeoff_gate.minimum_height_m,
            dwell_s=self._takeoff_gate.dwell_s,
            observed_height_m=self._takeoff_gate.height_m,
        )

    def _timestamp_us(self) -> int:
        return self.get_clock().now().nanoseconds // 1000

    def _vehicle_command(self, command: int, *, param1: float = math.nan) -> None:
        message = VehicleCommand()
        message.timestamp = self._timestamp_us()
        message.command = command
        message.param1 = param1
        message.param2 = math.nan
        message.param3 = math.nan
        message.param4 = math.nan
        message.param5 = math.nan
        message.param6 = math.nan
        message.param7 = math.nan
        message.target_system = self._target_system
        message.target_component = 1
        message.source_system = 1
        message.source_component = 191
        message.from_external = True
        self._command_pub.publish(message)

    def _publish_setpoint(self) -> None:
        timestamp = self._timestamp_us()
        control = OffboardControlMode()
        control.timestamp = timestamp
        control.position = self._setpoint_kind == "trajectory"
        control.attitude = self._setpoint_kind == "attitude"
        control.body_rate = self._setpoint_kind == "body_rate"
        self._control_pub.publish(control)
        if self._setpoint_kind == "trajectory":
            message = TrajectorySetpoint()
            message.timestamp = timestamp
            target_x = 0.0
            if self._workload_profile == "straight_line" and self._activation_ns is not None:
                target_x = straight_line_target(
                    (time.monotonic_ns() - self._activation_ns) / 1_000_000_000,
                    settle_s=self._motion_settle_s,
                    speed_m_s=self._motion_speed_m_s,
                    distance_m=self._motion_distance_m,
                )
            message.position = [target_x, 0.0, -self._altitude]
            message.velocity = [math.nan, math.nan, math.nan]
            message.acceleration = [math.nan, math.nan, math.nan]
            message.jerk = [math.nan, math.nan, math.nan]
            message.yaw = 0.0
            message.yawspeed = 0.0
            self._trajectory_pub.publish(message)
        elif self._setpoint_kind == "attitude":
            message = VehicleAttitudeSetpoint()
            message.timestamp = timestamp
            message.q_d = [1.0, 0.0, 0.0, 0.0]
            message.thrust_body = [0.0, 0.0, -0.6]
            self._attitude_pub.publish(message)
        else:
            message = VehicleRatesSetpoint()
            message.timestamp = timestamp
            message.roll = 0.0
            message.pitch = 0.0
            message.yaw = 0.0
            message.thrust_body = [0.0, 0.0, -0.6]
            self._rates_pub.publish(message)
        if not self._first_command_logged:
            self._log.append(
                "command_published",
                run_id=self._run_id,
                route="legacy_offboard",
                setpoint_kind=self._setpoint_kind,
            )
            self._first_command_logged = True

    def _publish_proof_of_life(self) -> None:
        message = OffboardControlMode()
        message.timestamp = self._timestamp_us()
        message.position = self._setpoint_kind == "trajectory"
        message.attitude = self._setpoint_kind == "attitude"
        message.body_rate = self._setpoint_kind == "body_rate"
        self._control_pub.publish(message)

    def _source_route_ready(self, now_ns: int) -> bool:
        """Require the preregistered public PX4 state before authority transfer."""
        if self._status is None:
            self._source_ready_ns = None
            return False
        if self._source_route == "internal_hold":
            ready = self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_LOITER
        elif self._source_route == "internal_rtl":
            ready = self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_RTL
        else:
            ready = self._status.nav_state != VehicleStatus.NAVIGATION_STATE_OFFBOARD
        if not ready:
            self._source_ready_ns = None
            return False
        if self._source_ready_ns is None:
            self._source_ready_ns = now_ns
        return now_ns - self._source_ready_ns >= self._source_dwell_ns

    def _tick(self) -> None:
        now_ns = time.monotonic_ns()
        self._update_physical_takeoff_state()
        elapsed = (now_ns - self._started_ns) / 1_000_000_000
        active_elapsed = (
            (time.monotonic_ns() - self._activation_ns) / 1_000_000_000
            if self._activation_ns is not None
            else 0.0
        )
        stalled = (
            self._fault_mode == "setpoint_stall"
            and self._activation_ns is not None
            and active_elapsed >= self._stall_after_s
            and (self._workload_profile != "straight_line" or self._motion_entered)
        )
        if stalled and not self._fault_logged:
            self._log.append(
                "fault_detected",
                run_id=self._run_id,
                reason="setpoint_stream_stalled_while_proof_of_life_continued",
                route="legacy_offboard",
                cycle=self._cycle,
            )
            self._fault_logged = True
        # Keep the public Offboard proof-of-life prestream active during a
        # non-terminal Hold/RTL dwell.  PX4 requires this before every later
        # re-entry just as it does before the first Offboard activation.
        if not self._landing_commanded:
            if not stalled:
                self._publish_setpoint()
            else:
                # Preserve the Offboard proof-of-life while withholding only
                # the selected stream; this is the freshness/health split.
                self._publish_proof_of_life()
        if (
            self._setpoint_kind != "trajectory"
            or self._source_route == "internal_rtl"
        ) and not self._ever_airborne:
            # Attitude/body-rate entry and an initial RTL source both require
            # an airborne public precondition. Establish it with ordinary PX4
            # vehicle commands before requesting the tested authority change.
            armed = (
                self._status is not None
                and self._status.arming_state == VehicleStatus.ARMING_STATE_ARMED
            )
            if not armed and (
                self._arm_sent_ns is None
                or now_ns - self._arm_sent_ns >= 1_000_000_000
            ):
                self._vehicle_command(
                    VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0
                )
                self._arm_sent_ns = now_ns
            if armed and (
                self._takeoff_sent_ns is None
                or now_ns - self._takeoff_sent_ns >= 1_000_000_000
            ):
                self._vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF)
                self._takeoff_sent_ns = now_ns
                if not self._takeoff_sent:
                    self._takeoff_sent = True
                    self._log.append("takeoff_requested", run_id=self._run_id)
            return
        if (
            self._source_route == "internal_rtl"
            and not self._commanded
            and self._status is not None
            and self._status.nav_state != VehicleStatus.NAVIGATION_STATE_AUTO_RTL
        ):
            if not self._source_setup_commanded:
                self._log.append(
                    "transition_requested",
                    run_id=self._run_id,
                    source_route="px4_internal",
                    target_route="internal_rtl",
                    setup_only=True,
                )
                self._source_setup_commanded = True
                self._log.append(
                    "source_route_requested",
                    run_id=self._run_id,
                    route="internal_rtl",
                )
            if (
                self._source_setup_sent_ns is None
                or now_ns - self._source_setup_sent_ns >= 1_000_000_000
            ):
                self._vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
                self._source_setup_sent_ns = now_ns
            return
        prestream_complete = elapsed >= self._prestream_s
        if self._setpoint_kind != "trajectory":
            prestream_complete = (
                self._airborne_ns is not None
                and now_ns - self._airborne_ns >= int(self._prestream_s * 1_000_000_000)
            )
        if not self._commanded and prestream_complete and self._source_route_ready(now_ns):
            self._log.append(
                "transition_requested",
                run_id=self._run_id,
                source_route=self._source_route,
                target_route="legacy_offboard",
            )
            self._vehicle_command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
            self._vehicle_command(
                VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                param1=float(VehicleStatus.NAVIGATION_STATE_OFFBOARD),
            )
            self._commanded = True
            self._log.append("offboard_requested", run_id=self._run_id)
        if (
            self._fault_mode == "process_exit"
            and self._activation_ns is not None
            and active_elapsed >= self._stall_after_s
        ):
            self._log.append(
                "fault_detected",
                run_id=self._run_id,
                reason="source_process_exit",
                route="legacy_offboard",
                cycle=self._cycle,
            )
            self._log.append("producer_process_exit", run_id=self._run_id)
            self._log.close()
            rclpy.shutdown()
            return
        if (
            not self._released
            and self._activation_ns is not None
            and active_elapsed >= self._active_s
        ):
            self._log.append(
                "completion",
                run_id=self._run_id,
                route="legacy_offboard",
                cycle=self._cycle,
            )
            self._log.append(
                "transition_requested",
                run_id=self._run_id,
                source_route="legacy_offboard",
                target_route=self._successor_route,
            )
            if self._successor_route == "internal_land":
                self._vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
            elif self._successor_route == "internal_rtl":
                self._vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
            else:
                self._vehicle_command(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER),
                )
            self._released = True
            self._landing_commanded = self._successor_route == "internal_land"
            self._log.append(
                "successor_requested",
                run_id=self._run_id,
                route=self._successor_route,
                cycle=self._cycle,
            )
        if (
            self._released
            and not self._landing_commanded
            and self._successor_observed_ns is not None
            and time.monotonic_ns() - self._successor_observed_ns
            >= int(self._successor_dwell_s * 1_000_000_000)
        ):
            if self._cycle + 1 < self._repeat_count:
                self._cycle += 1
                self._log.append(
                    "transition_requested",
                    run_id=self._run_id,
                    source_route=self._successor_route,
                    target_route="legacy_offboard",
                    cycle=self._cycle,
                )
                self._vehicle_command(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(VehicleStatus.NAVIGATION_STATE_OFFBOARD),
                )
                self._released = False
                self._activation_ns = None
                self._successor_observed_ns = None
                self._fault_logged = False
                self._log.append(
                    "producer_session_started",
                    run_id=self._run_id,
                    producer_session=f"offboard-{self._run_id}-{self._cycle}",
                    cycle=self._cycle,
                )
            else:
                self._log.append(
                    "transition_requested",
                    run_id=self._run_id,
                    source_route=self._successor_route,
                    target_route="internal_land",
                    cleanup_only=True,
                )
                self._vehicle_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                self._landing_commanded = True
                self._log.append("cleanup_land_requested", run_id=self._run_id)
        if self._status is not None and self._land is not None and self._landing_commanded:
            if (
                self._ever_armed
                and self._ever_offboard
                and self._ever_airborne
                and self._land.landed
                and self._status.arming_state == VehicleStatus.ARMING_STATE_DISARMED
            ):
                self._log.append("producer_completed", run_id=self._run_id)
                self._log.close()
                rclpy.shutdown()

    def destroy_node(self) -> bool:
        self._log.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = OffboardController()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
