from __future__ import annotations

import json
import math
import time
from pathlib import Path

import rclpy
from px4_msgs.msg import (
    RegisterExtComponentReply,
    VehicleCommand,
    VehicleCommandAck,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleStatus,
)
from rclpy.node import Node

from family_a_runtime.common import DurableJsonl, PX4_QOS, versioned_topic
from scripts.runtime.physical_readiness import PhysicalTakeoffGate
from scripts.runtime.moving_workload import progress_from_origin


class ExternalModeRequester(Node):
    def __init__(self) -> None:
        super().__init__("family_a_external_mode_requester")
        defaults = {
            "run_id": "",
            "lifecycle_path": "",
            "component_name": "Family A External",
            "active_s": 8.0,
            "successor_route": "internal_land",
            "successor_dwell_s": 2.0,
            "fault_mode": "normal",
            "rejection_observation_s": 6.0,
            "source_route": "px4_internal",
            "source_dwell_s": 1.0,
            "target_system": 1,
            "registration_handoff_path": "",
            "airborne_minimum_height_m": 0.5,
            "airborne_dwell_s": 0.5,
            "stall_after_s": 5.0,
            "workload_profile": "hover",
            "motion_entry_progress_m": 0.75,
            "motion_completion_progress_m": 2.5,
            "stall_request_path": "",
            "action_request_path": "",
            "repeat_count": 1,
            "scheduled_action": "",
            "producer_session_label": "",
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        self._run_id = self.get_parameter("run_id").value
        lifecycle_path = self.get_parameter("lifecycle_path").value
        self._component_name = self.get_parameter("component_name").value
        self._active_s = float(self.get_parameter("active_s").value)
        self._successor_route = self.get_parameter("successor_route").value
        self._successor_dwell_s = float(
            self.get_parameter("successor_dwell_s").value
        )
        self._fault_mode = self.get_parameter("fault_mode").value
        self._source_route = self.get_parameter("source_route").value
        self._source_dwell_ns = int(
            float(self.get_parameter("source_dwell_s").value) * 1_000_000_000
        )
        self._target_system = int(self.get_parameter("target_system").value)
        self._stall_after_s = float(self.get_parameter("stall_after_s").value)
        self._workload_profile = self.get_parameter("workload_profile").value
        self._motion_entry_progress_m = float(self.get_parameter("motion_entry_progress_m").value)
        self._motion_completion_progress_m = float(self.get_parameter("motion_completion_progress_m").value)
        self._repeat_count = int(self.get_parameter("repeat_count").value)
        self._scheduled_action = str(self.get_parameter("scheduled_action").value)
        self._session_label = str(self.get_parameter("producer_session_label").value)
        if self._repeat_count < 1:
            raise RuntimeError("repeat_count must be positive")
        if self._repeat_count > 1 and self._successor_route == "internal_land":
            raise RuntimeError("re-entry requires Hold or RTL as the intermediate successor")
        self._cycle = 0
        stall_request_path = self.get_parameter("stall_request_path").value
        action_request_path = self.get_parameter("action_request_path").value
        request_path = action_request_path or stall_request_path
        self._action_request_path = Path(request_path) if request_path else None
        registration_handoff_path = self.get_parameter(
            "registration_handoff_path"
        ).value
        self._registration_handoff_path = (
            Path(registration_handoff_path) if registration_handoff_path else None
        )
        self._registration_handoff_loaded = False
        self._takeoff_gate = PhysicalTakeoffGate(
            minimum_height_m=float(
                self.get_parameter("airborne_minimum_height_m").value
            ),
            dwell_s=float(self.get_parameter("airborne_dwell_s").value),
        )
        self._rejection_observation_s = float(
            self.get_parameter("rejection_observation_s").value
        )
        if not self._run_id or not lifecycle_path:
            raise RuntimeError("run_id and lifecycle_path are required")
        if self._successor_route not in {"internal_hold", "internal_rtl", "internal_land"}:
            raise RuntimeError("unsupported successor_route")
        if self._fault_mode not in {"normal", "process_exit", "setpoint_stall", "health_loss"}:
            raise RuntimeError("unsupported fault_mode")
        if self._source_route not in {"px4_internal", "internal_hold", "internal_rtl"}:
            raise RuntimeError("unsupported source_route")
        if self._source_dwell_ns < 0:
            raise RuntimeError("source_dwell_s must be non-negative")
        if not 1 <= self._target_system <= 255:
            raise RuntimeError("target_system must be in [1, 255]")
        if self._workload_profile not in {"hover", "straight_line"}:
            raise RuntimeError("unsupported workload_profile")
        self._log = DurableJsonl(lifecycle_path)
        self._mode_id: int | None = None
        self._registered_ns: int | None = None
        self._status: VehicleStatus | None = None
        self._arm_sent_ns: int | None = None
        self._takeoff_sent = False
        self._airborne = False
        self._mode_sent = False
        self._activated_ns: int | None = None
        self._land_sent = False
        self._released = False
        self._successor_observed_ns: int | None = None
        self._fault_logged = False
        self._land: VehicleLandDetected | None = None
        self._source_ready_ns: int | None = None
        self._latest_x_m: float | None = None
        self._motion_origin_x_m: float | None = None
        self._motion_entered = False
        self._motion_completed = False
        self._command_pub = self.create_publisher(
            VehicleCommand, "/fmu/in/vehicle_command", PX4_QOS
        )
        self.create_subscription(
            RegisterExtComponentReply,
            versioned_topic(
                "/fmu/out/register_ext_component_reply", RegisterExtComponentReply
            ),
            self._registration_reply,
            PX4_QOS,
        )
        self.create_subscription(
            VehicleCommandAck,
            versioned_topic("/fmu/out/vehicle_command_ack", VehicleCommandAck),
            self._command_ack_callback,
            PX4_QOS,
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
        self.create_timer(0.1, self._tick)
        self._log.append("requester_started", run_id=self._run_id)

    def _command_ack_callback(self, message: VehicleCommandAck) -> None:
        if (
            self._fault_mode != "health_loss"
            or not self._mode_sent
            or int(message.command) != VehicleCommand.VEHICLE_CMD_SET_NAV_STATE
        ):
            return
        if int(message.result) == VehicleCommandAck.VEHICLE_CMD_RESULT_ACCEPTED:
            return
        if not self._fault_logged:
            self._fault_logged = True
            self._log.append(
                "fault_detected",
                run_id=self._run_id,
                reason="activation_rejected_after_health_loss",
                route="dynamic_external_mode",
                result_code=2,
                px4_result_code=int(message.result),
                command=int(message.command),
            )
            self._command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
            self._land_sent = True
            self._log.append("cleanup_land_requested", run_id=self._run_id)

    @staticmethod
    def _name(value: object) -> str:
        try:
            return bytes(value).split(b"\0", 1)[0].decode("utf-8")
        except (TypeError, UnicodeDecodeError):
            return str(value).split("\0", 1)[0]

    def _registration_reply(self, message: RegisterExtComponentReply) -> None:
        if self._name(message.name) != self._component_name:
            return
        self._log.append(
            "registration_reply",
            run_id=self._run_id,
            success=bool(message.success),
            mode_id=int(message.mode_id),
            executor_id=int(message.mode_executor_id),
        )
        if message.success and message.mode_id >= 0:
            self._mode_id = int(message.mode_id)
            self._registered_ns = time.monotonic_ns()

    def _status_callback(self, message: VehicleStatus) -> None:
        self._status = message
        if self._mode_id is not None and int(message.nav_state) == self._mode_id:
            if self._activated_ns is None:
                self._activated_ns = time.monotonic_ns()
                self._log.append(
                    "dynamic_mode_observed_active",
                    run_id=self._run_id,
                    mode_id=self._mode_id,
                )
        elif self._activated_ns is not None and self._released:
            expected = {
                "internal_hold": VehicleStatus.NAVIGATION_STATE_AUTO_LOITER,
                "internal_rtl": VehicleStatus.NAVIGATION_STATE_AUTO_RTL,
                "internal_land": VehicleStatus.NAVIGATION_STATE_AUTO_LAND,
            }[self._successor_route]
            if int(message.nav_state) == expected and self._successor_observed_ns is None:
                self._successor_observed_ns = time.monotonic_ns()
                self._log.append(
                    "successor_observed_active",
                    run_id=self._run_id,
                    route=self._successor_route,
                    cycle=self._cycle,
                )
        elif (
            self._activated_ns is not None
            and self._fault_mode == "process_exit"
            and not self._fault_logged
        ):
            observed_route = {
                VehicleStatus.NAVIGATION_STATE_AUTO_LOITER: "internal_hold",
                VehicleStatus.NAVIGATION_STATE_AUTO_RTL: "internal_rtl",
                VehicleStatus.NAVIGATION_STATE_AUTO_LAND: "internal_land",
            }.get(int(message.nav_state))
            if observed_route is not None:
                self._fault_logged = True
                self._released = True
                self._successor_route = observed_route
                self._successor_observed_ns = time.monotonic_ns()
                self._log.append(
                    "fault_detected",
                    run_id=self._run_id,
                    reason="external_component_unresponsive",
                    route="dynamic_external_mode",
                )
                self._log.append(
                    "fallback_triggered",
                    run_id=self._run_id,
                    route=observed_route,
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
        if self._workload_profile != "straight_line" or self._activated_ns is None or self._latest_x_m is None:
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
        if self._airborne or not self._takeoff_gate.evaluate(time.monotonic_ns()):
            return
        self._airborne = True
        self._log.append(
            "physical_takeoff_ready",
            run_id=self._run_id,
            minimum_height_m=self._takeoff_gate.minimum_height_m,
            dwell_s=self._takeoff_gate.dwell_s,
            observed_height_m=self._takeoff_gate.height_m,
        )

    def _load_registration_handoff(self) -> None:
        if (
            self._registration_handoff_loaded
            or self._registration_handoff_path is None
            or not self._registration_handoff_path.is_file()
        ):
            return
        payload = json.loads(
            self._registration_handoff_path.read_text(encoding="utf-8")
        )
        expected = {
            "schema_version": "1.0",
            "run_id": self._run_id,
            "component_name": self._component_name,
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                raise RuntimeError(f"registration handoff {field} mismatch")
        mode_id = int(payload.get("mode_id", -1))
        if not 23 <= mode_id <= 30:
            raise RuntimeError("registration handoff mode_id is outside external slots")
        if self._mode_id is not None and self._mode_id != mode_id:
            raise RuntimeError("registration reply and handoff mode_id disagree")
        self._mode_id = mode_id
        if self._registered_ns is None:
            self._registered_ns = time.monotonic_ns()
        self._registration_handoff_loaded = True
        self._log.append(
            "registration_handoff_loaded",
            run_id=self._run_id,
            component_name=self._component_name,
            mode_id=mode_id,
        )

    def _command(self, command: int, *, param1: float = math.nan) -> None:
        message = VehicleCommand()
        message.timestamp = self.get_clock().now().nanoseconds // 1000
        message.command = command
        message.param1 = math.nan
        message.param2 = math.nan
        message.param3 = math.nan
        message.param4 = math.nan
        message.param5 = math.nan
        message.param6 = math.nan
        message.param7 = math.nan
        message.param1 = param1
        message.target_system = self._target_system
        message.target_component = 1
        message.source_system = 1
        message.source_component = 190
        message.from_external = True
        self._command_pub.publish(message)

    def _source_route_ready(self, now_ns: int) -> bool:
        if self._status is None:
            self._source_ready_ns = None
            return False
        if self._source_route == "internal_hold":
            ready = self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_LOITER
        elif self._source_route == "internal_rtl":
            ready = self._status.nav_state == VehicleStatus.NAVIGATION_STATE_AUTO_RTL
        else:
            ready = True
        if not ready:
            self._source_ready_ns = None
            return False
        if self._source_ready_ns is None:
            self._source_ready_ns = now_ns
        return now_ns - self._source_ready_ns >= self._source_dwell_ns

    def _tick(self) -> None:
        self._load_registration_handoff()
        self._update_physical_takeoff_state()
        if self._mode_id is None or self._status is None:
            return
        now = time.monotonic_ns()
        action_requested = (
            self._action_request_path.is_file()
            if self._action_request_path is not None
            else self._activated_ns is not None
            and now - self._activated_ns >= int(self._stall_after_s * 1_000_000_000)
        )
        if (
            self._fault_mode == "setpoint_stall"
            and self._activated_ns is not None
            and not self._fault_logged
            and action_requested
            and (self._workload_profile != "straight_line" or self._motion_entered)
        ):
            self._fault_logged = True
            self._log.append(
                "fault_detected",
                run_id=self._run_id,
                reason="setpoint_stream_stalled_while_mode_remained_active",
                route="dynamic_external_mode",
            )
        if self._land_sent:
            if (
                self._land is not None
                and self._land.landed
                and self._status.arming_state == VehicleStatus.ARMING_STATE_DISARMED
            ):
                self._log.append("requester_completed", run_id=self._run_id)
                self._log.close()
                rclpy.shutdown()
            return
        if self._status.arming_state != VehicleStatus.ARMING_STATE_ARMED:
            if not self._takeoff_sent:
                self._command(VehicleCommand.VEHICLE_CMD_NAV_TAKEOFF, param1=math.nan)
                self._takeoff_sent = True
                self._log.append("takeoff_requested", run_id=self._run_id)
            if self._arm_sent_ns is None or now - self._arm_sent_ns >= 1_000_000_000:
                self._command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)
                self._arm_sent_ns = now
            return
        health_loss_ready = (
            self._fault_mode != "health_loss"
            or (
                self._registered_ns is not None
                and now - self._registered_ns
                >= int(self._rejection_observation_s * 1_000_000_000)
            )
        )
        if (
            self._airborne
            and not self._mode_sent
            and self._source_route_ready(now)
            and health_loss_ready
        ):
            request_kind = (
                "activation_requested"
                if self._fault_mode == "health_loss"
                else "transition_requested"
            )
            self._log.append(
                request_kind,
                run_id=self._run_id,
                source_route=self._source_route,
                target_route="dynamic_external_mode",
            )
            self._command(
                VehicleCommand.VEHICLE_CMD_SET_NAV_STATE, param1=float(self._mode_id)
            )
            self._mode_sent = True
            return
        if (
            self._activated_ns is not None
            and not self._released
            and now - self._activated_ns >= int(self._active_s * 1_000_000_000)
        ):
            self._log.append(
                "completion",
                run_id=self._run_id,
                route="dynamic_external_mode",
            )
            self._log.append(
                "transition_requested",
                run_id=self._run_id,
                source_route="dynamic_external_mode",
                target_route=self._successor_route,
            )
            if self._successor_route == "internal_land":
                self._command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                self._land_sent = True
            elif self._successor_route == "internal_rtl":
                self._command(VehicleCommand.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH)
            else:
                self._command(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(VehicleStatus.NAVIGATION_STATE_AUTO_LOITER),
                )
            self._released = True
            self._log.append(
                "successor_requested",
                run_id=self._run_id,
                route=self._successor_route,
            )
        if (
            self._released
            and not self._land_sent
            and self._successor_observed_ns is not None
            and self._post_successor_due(now, action_requested)
        ):
            if self._cycle + 1 < self._repeat_count:
                # Re-enter the tested route from the installed safe route.  The
                # component stays registered, so the two entries are separated
                # by route epoch and activation identity rather than by name.
                self._cycle += 1
                self._log.append(
                    "transition_requested",
                    run_id=self._run_id,
                    source_route=self._successor_route,
                    target_route="dynamic_external_mode",
                    cycle=self._cycle,
                )
                self._command(
                    VehicleCommand.VEHICLE_CMD_SET_NAV_STATE,
                    param1=float(self._mode_id),
                )
                self._released = False
                self._activated_ns = None
                self._successor_observed_ns = None
                self._fault_logged = False
                return
            self._log.append(
                "transition_requested",
                run_id=self._run_id,
                source_route=self._successor_route,
                target_route="internal_land",
                cleanup_only=True,
            )
            self._command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
            self._land_sent = True
            self._log.append("cleanup_land_requested", run_id=self._run_id)

    def _post_successor_due(self, now: int, action_requested: bool) -> bool:
        """When the step after a successor installation may be taken.

        A policy-scheduled re-entry waits for the executor's request, so its
        timing is the decision's rather than a fixture constant.  Everything
        else keeps the preregistered dwell.
        """

        if self._scheduled_action == "re_enter_route_after_successor" and self._action_request_path is not None:
            return action_requested
        return (
            now - self._successor_observed_ns
            >= int(self._successor_dwell_s * 1_000_000_000)
        )

    def destroy_node(self) -> bool:
        self._log.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = ExternalModeRequester()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
