#!/usr/bin/env python3
"""Parameterized M1 offboard task player.

The node uses PX4 timestamps from /fmu/out topics as its event clock. It
publishes one finite TrajectorySetpoint stream for both backends; the selected
controller only changes which nav_state is requested at the configured switch
time.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rclpy
from rclpy.executors import ExternalShutdownException
from px4_msgs.msg import OffboardControlMode, RaptorStatus, TrajectorySetpoint, VehicleCommand
from px4_msgs.msg import VehicleLocalPosition, VehicleStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy


PX4_CUSTOM_MAIN_MODE_AUTO = 4
PX4_CUSTOM_MAIN_MODE_OFFBOARD = 6
PX4_CUSTOM_SUB_MODE_EXTERNAL1 = 11
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
NAV_STATE_OFFBOARD = 14
NAV_STATE_EXTERNAL1 = 23


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def finite_triplet(values: list[float] | tuple[float, float, float]) -> list[float]:
    out = [float(values[0]), float(values[1]), float(values[2])]
    if not all(math.isfinite(v) for v in out):
        raise ValueError(f"non-finite setpoint component: {values}")
    return out


@dataclass
class Event:
    name: str
    timestamp_us: int
    elapsed_s: float
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timestamp_us": self.timestamp_us,
            "elapsed_s": self.elapsed_s,
            "detail": self.detail,
        }


class M1OffboardTask(Node):
    def __init__(self, theta: dict[str, Any], controller: str, result_json: Path | None):
        super().__init__("m1_offboard_task")
        if controller not in {"classical", "raptor", "mcnn"}:
            raise ValueError(f"controller must be classical, raptor, or mcnn, got {controller}")

        self.theta = theta
        self.controller = controller
        self.result_json = result_json
        self.events: list[Event] = []

        timing = theta["timing"]
        setpoint = theta["setpoint"]
        self.switch_s = float(timing["controller_switch_s"])
        self.approach_start_s = float(timing.get("approach_start_s", self.switch_s))
        self.has_approach_stage = self.approach_start_s < self.switch_s - 1e-6
        self.trajectory_start_s = float(timing["trajectory_start_s"])
        self.mission_end_s = float(timing["mission_end_s"])
        self.mode_repeat_s = float(timing.get("mode_command_repeat_s", 0.5))
        self.mode_timeout_s = float(timing.get("mode_command_timeout_s", 6.0))
        self.external_mode_id = int(timing.get("external_mode_id", NAV_STATE_EXTERNAL1))
        if self.external_mode_id < NAV_STATE_EXTERNAL1:
            raise ValueError(f"external_mode_id must be >= {NAV_STATE_EXTERNAL1}, got {self.external_mode_id}")
        self.external_sub_mode = PX4_CUSTOM_SUB_MODE_EXTERNAL1 + (self.external_mode_id - NAV_STATE_EXTERNAL1)
        self.rate_hz = float(setpoint.get("rate_hz", 50.0))
        self.sim_speed_factor = max(1.0, float(os.environ.get("PX4_SIM_SPEED_FACTOR", "1") or 1.0))
        self.wall_timer_hz = self.rate_hz * self.sim_speed_factor
        max_wall_timer_hz = float(setpoint.get("max_wall_timer_hz", 800.0))
        if max_wall_timer_hz > 0:
            self.wall_timer_hz = min(self.wall_timer_hz, max_wall_timer_hz)
        self.hover_ned = finite_triplet(setpoint["hover_ned"])
        self.yaw_rad = float(setpoint.get("yaw_rad", 0.0))
        self.setpoint_type = str(setpoint.get("type", "step"))
        self.step_delta = finite_triplet(setpoint.get("step", {}).get("delta_ned", [0.0, 0.0, 0.0]))
        self.sine_axis = str(setpoint.get("sine", {}).get("axis", "x"))
        self.sine_amplitude_m = float(setpoint.get("sine", {}).get("amplitude_m", 0.0))
        self.sine_frequency_hz = float(setpoint.get("sine", {}).get("frequency_hz", 0.0))
        circle = setpoint.get("circle", {})
        self.circle_radius_m = float(circle.get("radius_m", 0.0))
        self.circle_frequency_hz = float(circle.get("frequency_hz", 0.0))
        self.circle_phase_rad = float(circle.get("phase_rad", 0.0))
        self.circle_z_amplitude_m = float(circle.get("z_amplitude_m", 0.0))
        self.circle_z_frequency_hz = float(circle.get("z_frequency_hz", self.circle_frequency_hz))

        self.origin_us: int | None = None
        self.now_us: int | None = None
        self.last_status: VehicleStatus | None = None
        self.last_local_position: VehicleLocalPosition | None = None
        self.last_raptor_status: RaptorStatus | None = None
        self.commanded_mode = False
        self.approach_mode_confirmed = False
        self.mode_confirmed = False
        self.last_mode_command_us = 0
        self.approach_active_us: int | None = None
        self.controller_active_us: int | None = None
        self.trajectory_start_us: int | None = None
        self.mission_end_us: int | None = None
        self.finished = False
        self.raptor_internal_reference_min: list[float] | None = None
        self.raptor_internal_reference_max: list[float] | None = None

        qos_pub = QoSProfile(depth=10)
        qos_sub = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        self.offboard_pub = self.create_publisher(OffboardControlMode, "/fmu/in/offboard_control_mode", qos_pub)
        self.setpoint_pub = self.create_publisher(TrajectorySetpoint, "/fmu/in/trajectory_setpoint", qos_pub)
        self.command_pub = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", qos_pub)
        self.create_subscription(
            VehicleStatus,
            f"/fmu/out/vehicle_status_v{VehicleStatus.MESSAGE_VERSION}",
            self.status_cb,
            qos_sub,
        )
        self.create_subscription(
            VehicleLocalPosition,
            f"/fmu/out/vehicle_local_position_v{VehicleLocalPosition.MESSAGE_VERSION}",
            self.local_position_cb,
            qos_sub,
        )
        self.create_subscription(RaptorStatus, "/fmu/out/raptor_status", self.raptor_status_cb, qos_sub)

        self.timer = self.create_timer(1.0 / self.wall_timer_hz, self.tick)
        self.get_logger().info(
            f"M1 task started controller={controller} tag={theta.get('tag')} "
            f"rate_hz={self.rate_hz} wall_timer_hz={self.wall_timer_hz} "
            f"PX4_SIM_SPEED_FACTOR={self.sim_speed_factor}"
        )

    def status_cb(self, msg: VehicleStatus) -> None:
        self.last_status = msg
        self.update_time(int(msg.timestamp))

    def local_position_cb(self, msg: VehicleLocalPosition) -> None:
        self.last_local_position = msg
        self.update_time(int(msg.timestamp))

    def raptor_status_cb(self, msg: RaptorStatus) -> None:
        self.last_raptor_status = msg
        if self.controller == "raptor" and self.controller_active_us is not None:
            values = [float(v) for v in msg.internal_reference_position]
            if all(math.isfinite(v) for v in values):
                if self.raptor_internal_reference_min is None:
                    self.raptor_internal_reference_min = values.copy()
                    self.raptor_internal_reference_max = values.copy()
                else:
                    self.raptor_internal_reference_min = [
                        min(a, b) for a, b in zip(self.raptor_internal_reference_min, values)
                    ]
                    self.raptor_internal_reference_max = [
                        max(a, b) for a, b in zip(self.raptor_internal_reference_max or values, values)
                    ]
        self.update_time(int(msg.timestamp))

    def update_time(self, timestamp_us: int) -> None:
        if timestamp_us <= 0:
            return
        if self.origin_us is None:
            self.origin_us = timestamp_us
            self.now_us = timestamp_us
            self.record_event("clock_origin", {"source": "first_px4_topic"})
            return
        self.now_us = max(self.now_us or timestamp_us, timestamp_us)

    def elapsed_s(self) -> float:
        if self.origin_us is None or self.now_us is None:
            return 0.0
        return (self.now_us - self.origin_us) / 1e6

    def record_event(self, name: str, detail: dict[str, Any] | None = None) -> None:
        if self.now_us is None:
            return
        event = Event(name, self.now_us, self.elapsed_s(), detail or {})
        self.events.append(event)
        print(json.dumps(event.as_dict(), sort_keys=True), flush=True)

    def current_setpoint(self, elapsed_s: float) -> list[float]:
        sp = self.hover_ned.copy()
        if elapsed_s < self.trajectory_start_s:
            return sp

        if self.trajectory_start_us is None and self.now_us is not None:
            self.trajectory_start_us = self.now_us
            self.record_event("trajectory_start", {"type": self.setpoint_type})

        t = elapsed_s - self.trajectory_start_s
        if self.setpoint_type == "step":
            return [sp[i] + self.step_delta[i] for i in range(3)]

        if self.setpoint_type == "sine":
            axis_index = {"x": 0, "y": 1, "z": 2}.get(self.sine_axis)
            if axis_index is None:
                raise ValueError(f"unsupported sine axis {self.sine_axis}")
            sp[axis_index] += self.sine_amplitude_m * math.sin(2.0 * math.pi * self.sine_frequency_hz * t)
            return sp

        if self.setpoint_type == "circle":
            omega_t = 2.0 * math.pi * self.circle_frequency_hz * t + self.circle_phase_rad
            sp[0] += self.circle_radius_m * math.sin(omega_t)
            sp[1] += self.circle_radius_m * math.cos(omega_t)
            if self.circle_z_amplitude_m:
                sp[2] += self.circle_z_amplitude_m * math.sin(
                    2.0 * math.pi * self.circle_z_frequency_hz * t + self.circle_phase_rad
                )
            return sp

        raise ValueError(f"unsupported setpoint type {self.setpoint_type}")

    def publish_offboard_control_mode(self) -> None:
        if self.now_us is None:
            return
        msg = OffboardControlMode()
        msg.timestamp = self.now_us
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        msg.thrust_and_torque = False
        msg.direct_actuator = False
        self.offboard_pub.publish(msg)

    def publish_trajectory_setpoint(self, sp: list[float]) -> None:
        if self.now_us is None:
            return
        msg = TrajectorySetpoint()
        msg.timestamp = self.now_us
        msg.position = [float(sp[0]), float(sp[1]), float(sp[2])]
        msg.velocity = [0.0, 0.0, 0.0]
        msg.acceleration = [0.0, 0.0, 0.0]
        msg.jerk = [0.0, 0.0, 0.0]
        msg.yaw = self.yaw_rad
        msg.yawspeed = 0.0
        self.setpoint_pub.publish(msg)

    def publish_vehicle_command(
        self,
        command: int,
        param1: float = 0.0,
        param2: float = 0.0,
        param3: float = 0.0,
        param4: float = 0.0,
        param5: float = 0.0,
        param6: float = 0.0,
        param7: float = 0.0,
    ) -> None:
        if self.now_us is None:
            return
        msg = VehicleCommand()
        msg.timestamp = self.now_us
        msg.param1 = float(param1)
        msg.param2 = float(param2)
        msg.param3 = float(param3)
        msg.param4 = float(param4)
        msg.param5 = float(param5)
        msg.param6 = float(param6)
        msg.param7 = float(param7)
        msg.command = int(command)
        msg.target_system = 1
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self.command_pub.publish(msg)

    def command_controller_mode(self, target_controller: str | None = None, *, final: bool = True) -> None:
        target_controller = target_controller or self.controller
        target_nav = NAV_STATE_OFFBOARD if target_controller == "classical" else self.external_mode_id
        if self.last_status and int(self.last_status.nav_state) == target_nav:
            if final and not self.mode_confirmed:
                self.mode_confirmed = True
                self.controller_active_us = self.now_us
                self.record_event("controller_active", {"nav_state": target_nav})
            elif not final and not self.approach_mode_confirmed:
                self.approach_mode_confirmed = True
                self.approach_active_us = self.now_us
                self.record_event("approach_active", {"nav_state": target_nav})
            return

        if self.now_us is None:
            return
        if self.now_us - self.last_mode_command_us < int(self.mode_repeat_s * 1e6):
            return

        self.last_mode_command_us = self.now_us
        self.commanded_mode = True
        phase = "final" if final else "approach"
        if target_controller == "classical":
            self.publish_vehicle_command(
                VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                PX4_CUSTOM_MAIN_MODE_OFFBOARD,
                0.0,
            )
            self.record_event(
                "mode_command",
                {"controller": target_controller, "phase": phase, "main": PX4_CUSTOM_MAIN_MODE_OFFBOARD},
            )
        else:
            self.publish_vehicle_command(
                VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                PX4_CUSTOM_MAIN_MODE_AUTO,
                self.external_sub_mode,
            )
            self.record_event(
                "mode_command",
                {
                    "controller": target_controller,
                    "phase": phase,
                    "main": PX4_CUSTOM_MAIN_MODE_AUTO,
                    "sub": self.external_sub_mode,
                    "mode_id": self.external_mode_id,
                },
            )

    def tick(self) -> None:
        if self.finished:
            return
        if self.now_us is None or self.origin_us is None:
            return

        elapsed = self.elapsed_s()
        sp = self.current_setpoint(elapsed)

        self.publish_offboard_control_mode()
        self.publish_trajectory_setpoint(sp)

        if self.has_approach_stage and elapsed >= self.approach_start_s and not self.approach_mode_confirmed:
            self.command_controller_mode("classical", final=(self.controller == "classical"))

        if elapsed >= self.switch_s and not self.mode_confirmed:
            self.command_controller_mode(self.controller, final=True)

        if (
            self.has_approach_stage
            and elapsed >= self.approach_start_s + self.mode_timeout_s
            and not self.approach_mode_confirmed
            and not (self.controller == "classical" and self.mode_confirmed)
        ):
            self.record_event(
                "approach_mode_timeout",
                {
                    "last_nav_state": int(self.last_status.nav_state) if self.last_status else None,
                },
            )
            self.finish(exit_code=2)
            return

        if elapsed >= self.switch_s + self.mode_timeout_s and not self.mode_confirmed:
            self.record_event(
                "controller_mode_timeout",
                {
                    "controller": self.controller,
                    "last_nav_state": int(self.last_status.nav_state) if self.last_status else None,
                },
            )
            self.finish(exit_code=2)
            return

        if elapsed >= self.mission_end_s:
            self.mission_end_us = self.now_us
            self.record_event("mission_end", {"setpoint_ned": sp})
            self.finish(exit_code=0)

    def finish(self, exit_code: int) -> None:
        self.finished = True
        if self.result_json:
            result = {
                "tag": self.theta.get("tag"),
                "controller": self.controller,
                "exit_code": exit_code,
                "sim_speed_factor": self.sim_speed_factor,
                "setpoint_rate_hz": self.rate_hz,
                "wall_timer_hz": self.wall_timer_hz,
                "origin_us": self.origin_us,
                "approach_start_s": self.approach_start_s,
                "approach_active_us": self.approach_active_us,
                "approach_mode_confirmed": self.approach_mode_confirmed,
                "controller_active_us": self.controller_active_us,
                "trajectory_start_us": self.trajectory_start_us,
                "mission_end_us": self.mission_end_us,
                "mode_confirmed": self.mode_confirmed,
                "external_mode_id": self.external_mode_id,
                "external_sub_mode": self.external_sub_mode,
                "last_nav_state": int(self.last_status.nav_state) if self.last_status else None,
                "last_position_ned": {
                    "x": float(self.last_local_position.x),
                    "y": float(self.last_local_position.y),
                    "z": float(self.last_local_position.z),
                }
                if self.last_local_position
                else None,
                "raptor_internal_reference_min": self.raptor_internal_reference_min,
                "raptor_internal_reference_max": self.raptor_internal_reference_max,
                "events": [event.as_dict() for event in self.events],
            }
            self.result_json.parent.mkdir(parents=True, exist_ok=True)
            with self.result_json.open("w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2, sort_keys=True)
                handle.write("\n")
        self.get_logger().info(f"M1 task finished exit_code={exit_code}")
        raise SystemExit(exit_code)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theta", type=Path, required=True)
    parser.add_argument("--controller", choices=["classical", "raptor", "mcnn"], required=True)
    parser.add_argument("--result-json", type=Path)
    args = parser.parse_args()

    theta = load_json(args.theta)
    rclpy.init()
    node = M1OffboardTask(theta, args.controller, args.result_json)
    try:
        rclpy.spin(node)
    except SystemExit as exc:
        return int(exc.code or 0)
    except ExternalShutdownException:
        return 130
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
