#!/usr/bin/env python3
"""Canonical, control-interface-independent Family A behavior core."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional, Sequence


Vector3 = tuple[float, float, float]


class BehaviorPhase(str, Enum):
    TAKEOFF_MARKER = "takeoff_phase_marker"
    HOVER = "hover"
    STRAIGHT_LINE = "straight_line"
    LOW_SPEED_TURN = "low_speed_turn"
    MISSION_COMPLETE = "mission_complete"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CanonicalCommand:
    timestamp: float
    behavior_phase: str
    position: Optional[Vector3]
    velocity: Optional[Vector3]
    acceleration: Optional[Vector3]
    yaw: Optional[float]
    termination_event: Optional[str]
    expected_route_event: Optional[str]

    def __post_init__(self) -> None:
        if not math.isfinite(self.timestamp):
            raise ValueError("timestamp must be finite")
        for field_name in ("position", "velocity", "acceleration"):
            value = getattr(self, field_name)
            if value is not None and (len(value) != 3 or not all(math.isfinite(v) for v in value)):
                raise ValueError(f"{field_name} must be a finite 3-vector")
        if self.yaw is not None and not math.isfinite(self.yaw):
            raise ValueError("yaw must be finite")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CommonBehaviorCore:
    """Deterministic low-risk sequence shared by Offboard and External Mode."""

    def __init__(
        self,
        hover_seconds: float = 3.0,
        straight_seconds: float = 5.0,
        turn_seconds: float = 4.0,
        straight_speed_m_s: float = 0.5,
        turn_speed_m_s: float = 0.3,
        turn_rate_rad_s: float = 0.15,
    ) -> None:
        values = (
            hover_seconds,
            straight_seconds,
            turn_seconds,
            straight_speed_m_s,
            turn_speed_m_s,
            turn_rate_rad_s,
        )
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError("durations, speeds, and turn rate must be finite and positive")
        self.hover_seconds = hover_seconds
        self.straight_seconds = straight_seconds
        self.turn_seconds = turn_seconds
        self.straight_speed_m_s = straight_speed_m_s
        self.turn_speed_m_s = turn_speed_m_s
        self.turn_rate_rad_s = turn_rate_rad_s

    @property
    def duration_seconds(self) -> float:
        return self.hover_seconds + self.straight_seconds + self.turn_seconds

    def takeoff_marker(self, timestamp: float) -> CanonicalCommand:
        return CanonicalCommand(
            timestamp=timestamp,
            behavior_phase=BehaviorPhase.TAKEOFF_MARKER.value,
            position=None,
            velocity=None,
            acceleration=None,
            yaw=None,
            termination_event=None,
            expected_route_event="internal_takeoff_active",
        )

    def command_at(self, elapsed_seconds: float, timestamp: float) -> CanonicalCommand:
        if not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if elapsed_seconds < self.hover_seconds:
            return self._velocity_command(timestamp, BehaviorPhase.HOVER, (0.0, 0.0, 0.0), 0.0)
        if elapsed_seconds < self.hover_seconds + self.straight_seconds:
            return self._velocity_command(
                timestamp,
                BehaviorPhase.STRAIGHT_LINE,
                (self.straight_speed_m_s, 0.0, 0.0),
                0.0,
            )
        if elapsed_seconds < self.duration_seconds:
            turn_elapsed = elapsed_seconds - self.hover_seconds - self.straight_seconds
            yaw = self.turn_rate_rad_s * turn_elapsed
            velocity = (
                self.turn_speed_m_s * math.cos(yaw),
                self.turn_speed_m_s * math.sin(yaw),
                0.0,
            )
            return self._velocity_command(timestamp, BehaviorPhase.LOW_SPEED_TURN, velocity, yaw)
        return self.mission_complete(timestamp)

    def mission_complete(self, timestamp: float) -> CanonicalCommand:
        return CanonicalCommand(
            timestamp=timestamp,
            behavior_phase=BehaviorPhase.MISSION_COMPLETE.value,
            position=None,
            velocity=(0.0, 0.0, 0.0),
            acceleration=None,
            yaw=None,
            termination_event="mission_complete",
            expected_route_event="release_to_internal_route",
        )

    def cancel(self, timestamp: float) -> CanonicalCommand:
        return CanonicalCommand(
            timestamp=timestamp,
            behavior_phase=BehaviorPhase.CANCELLED.value,
            position=None,
            velocity=(0.0, 0.0, 0.0),
            acceleration=None,
            yaw=None,
            termination_event="cancel",
            expected_route_event="release_to_internal_route",
        )

    @staticmethod
    def _velocity_command(
        timestamp: float, phase: BehaviorPhase, velocity: Sequence[float], yaw: float
    ) -> CanonicalCommand:
        return CanonicalCommand(
            timestamp=timestamp,
            behavior_phase=phase.value,
            position=None,
            velocity=(float(velocity[0]), float(velocity[1]), float(velocity[2])),
            acceleration=None,
            yaw=yaw,
            termination_event=None,
            expected_route_event="external_route_active",
        )
