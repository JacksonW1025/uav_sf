#!/usr/bin/env python3
"""Continuous safety decisions for Family A flight execution."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SafetyLimits:
    heartbeat_timeout_ns: int
    collector_timeout_ns: int
    run_timeout_ns: int
    maximum_altitude_loss_m: float
    maximum_horizontal_speed_m_s: float
    maximum_vertical_speed_m_s: float
    maximum_attitude_excursion_deg: float
    maximum_body_rate_rad_s: float

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "SafetyLimits":
        limits = cls(**value)
        if any(number <= 0 for number in limits.__dict__.values()):
            raise ValueError("every safety limit must be positive")
        return limits


@dataclass
class SafetyState:
    started_ns: int
    last_heartbeat_ns: int
    collectors: dict[str, int] = field(default_factory=dict)
    stopped_reason: str | None = None


class SafetySupervisor:
    def __init__(
        self, limits: SafetyLimits, *, started_ns: int, required_collectors: set[str]
    ) -> None:
        if not required_collectors:
            raise ValueError("at least one collector is required")
        self.limits = limits
        self.state = SafetyState(
            started_ns=started_ns,
            last_heartbeat_ns=started_ns,
            collectors={name: started_ns for name in required_collectors},
        )

    def _stop(self, reason: str) -> dict[str, str]:
        if self.state.stopped_reason is None:
            self.state.stopped_reason = reason
        return {
            "decision": "STOP_AND_INSTALL_FALLBACK",
            "reason": self.state.stopped_reason,
            "fallback": "internal_land",
        }

    def observe(self, event: dict[str, Any], *, now_ns: int) -> dict[str, str]:
        if self.state.stopped_reason is not None:
            return self._stop(self.state.stopped_reason)
        kind = event.get("kind")
        if kind == "supervisor_heartbeat":
            self.state.last_heartbeat_ns = now_ns
        elif kind == "collector_heartbeat":
            collector = str(event.get("collector", ""))
            if collector not in self.state.collectors:
                return self._stop("unknown_collector")
            self.state.collectors[collector] = now_ns
        elif kind == "collector_failure":
            return self._stop("collector_failure")
        elif kind == "clock_failure":
            return self._stop("clock_failure")
        elif kind == "telemetry":
            numeric = {
                "altitude_loss_m": self.limits.maximum_altitude_loss_m,
                "horizontal_speed_m_s": self.limits.maximum_horizontal_speed_m_s,
                "vertical_speed_m_s": self.limits.maximum_vertical_speed_m_s,
                "attitude_excursion_deg": self.limits.maximum_attitude_excursion_deg,
                "body_rate_rad_s": self.limits.maximum_body_rate_rad_s,
            }
            for field, bound in numeric.items():
                value = event.get(field)
                if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    return self._stop(f"invalid_{field}")
                magnitude = float(value) if field == "altitude_loss_m" else abs(float(value))
                if magnitude > bound:
                    return self._stop(f"{field}_exceeded")
            if event.get("unexpected_ground_contact") is True:
                return self._stop("unexpected_ground_contact")
        else:
            return self._stop("invalid_supervisor_event")
        return {"decision": "CONTINUE", "reason": "within_limits", "fallback": ""}

    def check_time(self, *, now_ns: int) -> dict[str, str]:
        if now_ns - self.state.started_ns > self.limits.run_timeout_ns:
            return self._stop("run_timeout")
        if now_ns - self.state.last_heartbeat_ns > self.limits.heartbeat_timeout_ns:
            return self._stop("heartbeat_timeout")
        if any(
            now_ns - timestamp > self.limits.collector_timeout_ns
            for timestamp in self.state.collectors.values()
        ):
            return self._stop("collector_timeout")
        return {"decision": "CONTINUE", "reason": "within_limits", "fallback": ""}
