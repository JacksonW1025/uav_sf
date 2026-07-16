#!/usr/bin/env python3
"""ROS 2 Offboard adapter for canonical Family A behavior commands."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Optional

from scripts.behavior.common_behavior_core import CanonicalCommand


MAV_CMD_DO_SET_MODE = 176
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1.0
PX4_CUSTOM_MAIN_MODE_AUTO = 4.0
PX4_CUSTOM_MAIN_MODE_OFFBOARD = 6.0
PX4_CUSTOM_SUB_MODE_AUTO_LOITER = 3.0


@dataclass(frozen=True)
class OffboardPublication:
    producer_timestamp_us: int
    publish_sequence: int
    proof_of_life: dict[str, object]
    trajectory_setpoint: dict[str, object]
    expected_route_event: Optional[str]


class OffboardAdapterContract:
    """Pure contract layer; ROS message construction is a separate concern."""

    def __init__(self, producer_identity: str = "uav_sf.offboard_adapter") -> None:
        if not producer_identity.strip():
            raise ValueError("producer_identity is required")
        self.producer_identity = producer_identity
        self._sequence = 0

    @property
    def next_sequence(self) -> int:
        return self._sequence

    def publication_for(self, command: CanonicalCommand, producer_timestamp_us: int) -> OffboardPublication:
        if producer_timestamp_us < 0:
            raise ValueError("producer_timestamp_us must be non-negative")
        controls = {
            "position": command.position is not None,
            "velocity": command.velocity is not None,
            "acceleration": command.acceleration is not None,
            "attitude": False,
            "body_rate": False,
            "thrust_and_torque": False,
            "direct_actuator": False,
        }
        setpoint = {
            "timestamp": producer_timestamp_us,
            "position": command.position or (math.nan, math.nan, math.nan),
            "velocity": command.velocity or (math.nan, math.nan, math.nan),
            "acceleration": command.acceleration or (math.nan, math.nan, math.nan),
            "yaw": command.yaw if command.yaw is not None else math.nan,
            "behavior_phase": command.behavior_phase,
            "termination_event": command.termination_event,
            "producer_identity": self.producer_identity,
        }
        publication = OffboardPublication(
            producer_timestamp_us=producer_timestamp_us,
            publish_sequence=self._sequence,
            proof_of_life={"timestamp": producer_timestamp_us, **controls},
            trajectory_setpoint=setpoint,
            expected_route_event=command.expected_route_event,
        )
        self._sequence += 1
        return publication

    @staticmethod
    def mode_request(producer_timestamp_us: int) -> dict[str, object]:
        return {
            "timestamp": producer_timestamp_us,
            "command": MAV_CMD_DO_SET_MODE,
            "param1": MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            "param2": PX4_CUSTOM_MAIN_MODE_OFFBOARD,
            "param3": 0.0,
            "event": "offboard_mode_requested",
        }

    @staticmethod
    def release_request(producer_timestamp_us: int) -> dict[str, object]:
        return {
            "timestamp": producer_timestamp_us,
            "command": MAV_CMD_DO_SET_MODE,
            "param1": MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            "param2": PX4_CUSTOM_MAIN_MODE_AUTO,
            "param3": PX4_CUSTOM_SUB_MODE_AUTO_LOITER,
            "event": "internal_hold_requested",
        }


class Px4OffboardAdapter:
    """Thin ROS 2 publisher that materializes the pure adapter contract."""

    def __init__(
        self,
        node: object,
        producer_identity: str = "uav_sf.offboard_adapter",
        event_sink: Optional[Callable[[dict[str, object]], None]] = None,
    ) -> None:
        try:
            from px4_msgs.msg import OffboardControlMode, TrajectorySetpoint, VehicleCommand
        except ImportError as exc:  # pragma: no cover - exercised in the ROS environment
            raise RuntimeError("px4_msgs is required to construct Px4OffboardAdapter") from exc
        self._types = (OffboardControlMode, TrajectorySetpoint, VehicleCommand)
        self._node = node
        self.contract = OffboardAdapterContract(producer_identity)
        self._event_sink = event_sink or (lambda event: None)
        self._control_mode_pub = node.create_publisher(OffboardControlMode, "/fmu/in/offboard_control_mode", 10)
        self._setpoint_pub = node.create_publisher(TrajectorySetpoint, "/fmu/in/trajectory_setpoint", 10)
        self._command_pub = node.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)

    def publish(self, command: CanonicalCommand, producer_timestamp_us: Optional[int] = None) -> int:
        timestamp_us = producer_timestamp_us if producer_timestamp_us is not None else time.monotonic_ns() // 1000
        publication = self.contract.publication_for(command, timestamp_us)
        OffboardControlMode, TrajectorySetpoint, _ = self._types

        control = OffboardControlMode()
        for name, value in publication.proof_of_life.items():
            if hasattr(control, name):
                setattr(control, name, value)
        setpoint = TrajectorySetpoint()
        setpoint.timestamp = timestamp_us
        setpoint.position = list(publication.trajectory_setpoint["position"])
        setpoint.velocity = list(publication.trajectory_setpoint["velocity"])
        setpoint.acceleration = list(publication.trajectory_setpoint["acceleration"])
        setpoint.yaw = publication.trajectory_setpoint["yaw"]
        self._control_mode_pub.publish(control)
        self._setpoint_pub.publish(setpoint)
        self._event_sink(
            {
                "event_type": "offboard_publish",
                "producer_timestamp": timestamp_us,
                "publish_sequence": publication.publish_sequence,
                "producer_identity": self.contract.producer_identity,
                "behavior_phase": command.behavior_phase,
            }
        )
        return publication.publish_sequence

    def request_mode(self, release: bool = False, producer_timestamp_us: Optional[int] = None) -> None:
        timestamp_us = producer_timestamp_us if producer_timestamp_us is not None else time.monotonic_ns() // 1000
        plan = self.contract.release_request(timestamp_us) if release else self.contract.mode_request(timestamp_us)
        _, _, VehicleCommand = self._types
        message = VehicleCommand()
        message.timestamp = timestamp_us
        message.command = int(plan["command"])
        message.param1 = float(plan["param1"])
        message.param2 = float(plan["param2"])
        message.param3 = float(plan["param3"])
        message.target_system = 1
        message.target_component = 1
        message.source_system = 1
        message.source_component = 1
        message.from_external = True
        self._command_pub.publish(message)
        self._event_sink({**plan, "producer_identity": self.contract.producer_identity})

    def release(self, producer_timestamp_us: Optional[int] = None) -> None:
        self.request_mode(release=True, producer_timestamp_us=producer_timestamp_us)
