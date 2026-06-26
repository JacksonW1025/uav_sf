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
from px4_msgs.msg import VehicleAngularVelocity, VehicleAttitude, VehicleLocalPosition, VehicleStatus
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


def px4_topic_candidates(base: str, msg_type: type) -> list[str]:
    fallback_versions = {
        "VehicleStatus": 4,
        "VehicleLocalPosition": 1,
        "VehicleAttitude": 0,
        "VehicleAngularVelocity": 0,
    }
    version = getattr(msg_type, "MESSAGE_VERSION", fallback_versions.get(msg_type.__name__))
    if version is None:
        return [base]
    version = int(version)
    if version > 0:
        return [f"{base}_v{version}", base]
    return [base, f"{base}_v0"]


def quat_to_rpy(q: list[float] | tuple[float, float, float, float]) -> tuple[float, float, float]:
    q0, q1, q2, q3 = [float(value) for value in q]
    roll = math.atan2(2.0 * (q0 * q1 + q2 * q3), 1.0 - 2.0 * (q1 * q1 + q2 * q2))
    sin_pitch = max(-1.0, min(1.0, 2.0 * (q0 * q2 - q3 * q1)))
    pitch = math.asin(sin_pitch)
    yaw = math.atan2(2.0 * (q0 * q3 + q1 * q2), 1.0 - 2.0 * (q2 * q2 + q3 * q3))
    return roll, pitch, yaw


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
        step = setpoint.get("step", {})
        self.step_delta = finite_triplet(step.get("delta_ned", [0.0, 0.0, 0.0]))
        self.step_start_s = float(step.get("start_s", self.trajectory_start_s))
        self.step_recorded = False
        ramp = setpoint.get("ramp", {})
        self.ramp_delta = finite_triplet(ramp.get("delta_ned", [0.0, 0.0, 0.0]))
        self.ramp_duration_s = float(ramp.get("duration_s", 1.0))
        self.sine_axis = str(setpoint.get("sine", {}).get("axis", "x"))
        self.sine_amplitude_m = float(setpoint.get("sine", {}).get("amplitude_m", 0.0))
        self.sine_frequency_hz = float(setpoint.get("sine", {}).get("frequency_hz", 0.0))
        circle = setpoint.get("circle", {})
        self.circle_radius_m = float(circle.get("radius_m", 0.0))
        self.circle_frequency_hz = float(circle.get("frequency_hz", 0.0))
        self.circle_phase_rad = float(circle.get("phase_rad", 0.0))
        self.circle_z_amplitude_m = float(circle.get("z_amplitude_m", 0.0))
        self.circle_z_frequency_hz = float(circle.get("z_frequency_hz", self.circle_frequency_hz))
        self.feedforward = bool(setpoint.get("feedforward", False))
        post_switch = setpoint.get("post_switch", {})
        if post_switch is None:
            post_switch = {}
        self.post_switch_type = str(post_switch.get("type", "")).lower()
        self.post_switch_enabled = bool(post_switch) and self.post_switch_type not in {"", "none"}
        self.post_switch_hover_ned = finite_triplet(post_switch.get("hover_ned", self.hover_ned))
        self.post_switch_recorded = False
        self.activation_trigger = setpoint.get("activation_trigger") or {}
        self.state_trigger_enabled = bool(self.activation_trigger.get("enabled", False))
        self.state_trigger_start_s = float(self.activation_trigger.get("start_s", self.trajectory_start_s))
        self.state_trigger_deadline_s = float(
            self.activation_trigger.get("deadline_s", max(self.switch_s, self.state_trigger_start_s))
        )
        self.state_trigger_switch_delay_s = float(self.activation_trigger.get("switch_delay_s", 0.0))
        self.state_trigger_fired = not self.state_trigger_enabled
        self.state_trigger_state: dict[str, Any] | None = None
        self.state_trigger_us: int | None = None
        self.state_trigger_max_observed: dict[str, Any] | None = None

        self.origin_us: int | None = None
        self.now_us: int | None = None
        self.last_status: VehicleStatus | None = None
        self.last_local_position: VehicleLocalPosition | None = None
        self.last_truth_attitude: VehicleAttitude | None = None
        self.last_truth_rates: VehicleAngularVelocity | None = None
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
        for topic in px4_topic_candidates("/fmu/out/vehicle_status", VehicleStatus):
            self.create_subscription(VehicleStatus, topic, self.status_cb, qos_sub)
        for topic in px4_topic_candidates("/fmu/out/vehicle_local_position", VehicleLocalPosition):
            self.create_subscription(VehicleLocalPosition, topic, self.local_position_cb, qos_sub)
        for topic in px4_topic_candidates("/fmu/out/vehicle_attitude_groundtruth", VehicleAttitude):
            self.create_subscription(VehicleAttitude, topic, self.truth_attitude_cb, qos_sub)
        for topic in px4_topic_candidates("/fmu/out/vehicle_angular_velocity_groundtruth", VehicleAngularVelocity):
            self.create_subscription(VehicleAngularVelocity, topic, self.truth_rates_cb, qos_sub)
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

    def truth_attitude_cb(self, msg: VehicleAttitude) -> None:
        self.last_truth_attitude = msg
        self.update_time(int(msg.timestamp))

    def truth_rates_cb(self, msg: VehicleAngularVelocity) -> None:
        self.last_truth_rates = msg
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
        return self.current_trajectory(elapsed_s)[0]

    def current_trajectory(self, elapsed_s: float) -> tuple[list[float], list[float], list[float]]:
        if self.post_switch_enabled and self.state_trigger_fired and elapsed_s >= self.switch_s:
            if not self.post_switch_recorded:
                self.post_switch_recorded = True
                self.record_event(
                    "post_switch_setpoint",
                    {"type": self.post_switch_type, "state_trigger": self.state_trigger_state},
                )
            if self.post_switch_type == "hover":
                return self.post_switch_hover_ned.copy(), [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            raise ValueError(f"unsupported post_switch type {self.post_switch_type}")

        sp = self.hover_ned.copy()
        if elapsed_s < self.trajectory_start_s:
            return sp, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]

        if self.trajectory_start_us is None and self.now_us is not None:
            self.trajectory_start_us = self.now_us
            self.record_event("trajectory_start", {"type": self.setpoint_type})

        t = elapsed_s - self.trajectory_start_s
        if self.setpoint_type == "step":
            if elapsed_s < self.step_start_s:
                return sp, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            if not self.step_recorded:
                self.step_recorded = True
                self.record_event("setpoint_step", {"delta_ned": self.step_delta, "start_s": self.step_start_s})
            return [sp[i] + self.step_delta[i] for i in range(3)], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]

        if self.setpoint_type == "ramp":
            if self.ramp_duration_s <= 0.0:
                return [sp[i] + self.ramp_delta[i] for i in range(3)], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            alpha = min(1.0, max(0.0, t / self.ramp_duration_s))
            velocity = [0.0, 0.0, 0.0]
            if self.feedforward and 0.0 <= t <= self.ramp_duration_s:
                velocity = [self.ramp_delta[i] / self.ramp_duration_s for i in range(3)]
            return [sp[i] + self.ramp_delta[i] * alpha for i in range(3)], velocity, [0.0, 0.0, 0.0]

        if self.setpoint_type == "sine":
            axis_index = {"x": 0, "y": 1, "z": 2}.get(self.sine_axis)
            if axis_index is None:
                raise ValueError(f"unsupported sine axis {self.sine_axis}")
            omega = 2.0 * math.pi * self.sine_frequency_hz
            sp[axis_index] += self.sine_amplitude_m * math.sin(omega * t)
            velocity = [0.0, 0.0, 0.0]
            acceleration = [0.0, 0.0, 0.0]
            if self.feedforward:
                velocity[axis_index] = self.sine_amplitude_m * omega * math.cos(omega * t)
                acceleration[axis_index] = -self.sine_amplitude_m * omega * omega * math.sin(omega * t)
            return sp, velocity, acceleration

        if self.setpoint_type == "circle":
            omega = 2.0 * math.pi * self.circle_frequency_hz
            omega_t = omega * t + self.circle_phase_rad
            sp[0] += self.circle_radius_m * math.sin(omega_t)
            sp[1] += self.circle_radius_m * math.cos(omega_t)
            velocity = [0.0, 0.0, 0.0]
            acceleration = [0.0, 0.0, 0.0]
            if self.feedforward:
                velocity[0] = self.circle_radius_m * omega * math.cos(omega_t)
                velocity[1] = -self.circle_radius_m * omega * math.sin(omega_t)
                acceleration[0] = -self.circle_radius_m * omega * omega * math.sin(omega_t)
                acceleration[1] = -self.circle_radius_m * omega * omega * math.cos(omega_t)
            if self.circle_z_amplitude_m:
                z_omega = 2.0 * math.pi * self.circle_z_frequency_hz
                z_phase = z_omega * t + self.circle_phase_rad
                sp[2] += self.circle_z_amplitude_m * math.sin(z_phase)
                if self.feedforward:
                    velocity[2] = self.circle_z_amplitude_m * z_omega * math.cos(z_phase)
                    acceleration[2] = -self.circle_z_amplitude_m * z_omega * z_omega * math.sin(z_phase)
            return sp, velocity, acceleration

        raise ValueError(f"unsupported setpoint type {self.setpoint_type}")

    def truth_state_snapshot(self) -> dict[str, Any] | None:
        if self.now_us is None or self.last_truth_attitude is None or self.last_truth_rates is None:
            return None
        roll, pitch, yaw = quat_to_rpy(self.last_truth_attitude.q)
        omega = [float(value) for value in self.last_truth_rates.xyz]
        omega_norm = math.sqrt(sum(value * value for value in omega))
        return {
            "timestamp_us": self.now_us,
            "attitude_timestamp_us": int(self.last_truth_attitude.timestamp),
            "angular_velocity_timestamp_us": int(self.last_truth_rates.timestamp),
            "elapsed_s": self.elapsed_s(),
            "roll_deg": math.degrees(roll),
            "pitch_deg": math.degrees(pitch),
            "yaw_deg": math.degrees(yaw),
            "roll_pitch_abs_deg": max(abs(math.degrees(roll)), abs(math.degrees(pitch))),
            "angular_rate_xyz_rad_s": omega,
            "angular_rate_norm_rad_s": omega_norm,
            "roll_rate_abs_rad_s": abs(omega[0]),
            "pitch_rate_abs_rad_s": abs(omega[1]),
            "yaw_rate_abs_rad_s": abs(omega[2]),
        }

    def update_trigger_max(self, state: dict[str, Any]) -> None:
        if self.state_trigger_max_observed is None:
            self.state_trigger_max_observed = dict(state)
            return
        current = self.state_trigger_max_observed
        if state["roll_pitch_abs_deg"] > current.get("roll_pitch_abs_deg", -math.inf):
            current["roll_pitch_abs_deg"] = state["roll_pitch_abs_deg"]
            current["roll_pitch_abs_state"] = dict(state)
        if state["angular_rate_norm_rad_s"] > current.get("angular_rate_norm_rad_s", -math.inf):
            current["angular_rate_norm_rad_s"] = state["angular_rate_norm_rad_s"]
            current["angular_rate_norm_state"] = dict(state)

    def trigger_condition_met(self, state: dict[str, Any]) -> bool:
        checks = [
            ("roll_abs_min_deg", abs(state["roll_deg"]), ">="),
            ("roll_abs_max_deg", abs(state["roll_deg"]), "<="),
            ("pitch_abs_min_deg", abs(state["pitch_deg"]), ">="),
            ("pitch_abs_max_deg", abs(state["pitch_deg"]), "<="),
            ("roll_pitch_abs_min_deg", state["roll_pitch_abs_deg"], ">="),
            ("roll_pitch_abs_max_deg", state["roll_pitch_abs_deg"], "<="),
            ("angular_rate_norm_min_rad_s", state["angular_rate_norm_rad_s"], ">="),
            ("angular_rate_norm_max_rad_s", state["angular_rate_norm_rad_s"], "<="),
            ("roll_rate_abs_min_rad_s", state["roll_rate_abs_rad_s"], ">="),
            ("roll_rate_abs_max_rad_s", state["roll_rate_abs_rad_s"], "<="),
            ("pitch_rate_abs_min_rad_s", state["pitch_rate_abs_rad_s"], ">="),
            ("pitch_rate_abs_max_rad_s", state["pitch_rate_abs_rad_s"], "<="),
            ("yaw_rate_abs_min_rad_s", state["yaw_rate_abs_rad_s"], ">="),
            ("yaw_rate_abs_max_rad_s", state["yaw_rate_abs_rad_s"], "<="),
        ]
        for key, value, op in checks:
            if key not in self.activation_trigger:
                continue
            threshold = float(self.activation_trigger[key])
            if op == ">=" and value < threshold:
                return False
            if op == "<=" and value > threshold:
                return False
        max_topic_age_s = float(self.activation_trigger.get("max_topic_age_s", 0.25))
        attitude_age_s = abs(state["timestamp_us"] - state["attitude_timestamp_us"]) / 1e6
        rate_age_s = abs(state["timestamp_us"] - state["angular_velocity_timestamp_us"]) / 1e6
        return attitude_age_s <= max_topic_age_s and rate_age_s <= max_topic_age_s

    def maybe_fire_state_trigger(self, elapsed_s: float) -> None:
        if not self.state_trigger_enabled or self.state_trigger_fired:
            return
        state = self.truth_state_snapshot()
        if state is not None and elapsed_s >= self.state_trigger_start_s:
            self.update_trigger_max(state)
            if self.trigger_condition_met(state):
                self.state_trigger_fired = True
                self.state_trigger_state = dict(state)
                self.state_trigger_us = self.now_us
                self.switch_s = elapsed_s + max(0.0, self.state_trigger_switch_delay_s)
                self.record_event(
                    "state_trigger",
                    {
                        "trigger": self.activation_trigger,
                        "state": self.state_trigger_state,
                        "controller_switch_s": self.switch_s,
                    },
                )
        if not self.state_trigger_fired and elapsed_s >= self.state_trigger_deadline_s:
            self.record_event(
                "state_trigger_timeout",
                {
                    "trigger": self.activation_trigger,
                    "max_observed": self.state_trigger_max_observed,
                    "last_state": state,
                },
            )
            self.finish(exit_code=3)

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

    def publish_trajectory_setpoint(
        self,
        sp: list[float],
        velocity: list[float] | None = None,
        acceleration: list[float] | None = None,
    ) -> None:
        if self.now_us is None:
            return
        msg = TrajectorySetpoint()
        msg.timestamp = self.now_us
        msg.position = [float(sp[0]), float(sp[1]), float(sp[2])]
        velocity = velocity or [0.0, 0.0, 0.0]
        acceleration = acceleration or [0.0, 0.0, 0.0]
        msg.velocity = [float(velocity[0]), float(velocity[1]), float(velocity[2])]
        msg.acceleration = [float(acceleration[0]), float(acceleration[1]), float(acceleration[2])]
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
        self.maybe_fire_state_trigger(elapsed)
        sp, velocity, acceleration = self.current_trajectory(elapsed)

        self.publish_offboard_control_mode()
        self.publish_trajectory_setpoint(sp, velocity, acceleration)

        if self.has_approach_stage and elapsed >= self.approach_start_s and not self.approach_mode_confirmed:
            self.command_controller_mode("classical", final=(self.controller == "classical" and not self.state_trigger_enabled))

        if self.state_trigger_fired and elapsed >= self.switch_s and not self.mode_confirmed:
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

        if self.state_trigger_fired and elapsed >= self.switch_s + self.mode_timeout_s and not self.mode_confirmed:
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
                "state_trigger_enabled": self.state_trigger_enabled,
                "state_trigger_fired": self.state_trigger_fired,
                "state_trigger_us": self.state_trigger_us,
                "state_trigger_state": self.state_trigger_state,
                "state_trigger_max_observed": self.state_trigger_max_observed,
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
