"""Shared live/offline predicate for a physically established takeoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


MINIMUM_AIRBORNE_HEIGHT_M = 0.5
AIRBORNE_DWELL_S = 0.5
MAXIMUM_SAMPLE_AGE_S = 1.0


@dataclass
class PhysicalTakeoffGate:
    """Latch only after fresh land and position evidence agree for a dwell."""

    minimum_height_m: float = MINIMUM_AIRBORNE_HEIGHT_M
    dwell_s: float = AIRBORNE_DWELL_S
    maximum_sample_age_s: float = MAXIMUM_SAMPLE_AGE_S

    def __post_init__(self) -> None:
        if self.minimum_height_m <= 0:
            raise ValueError("minimum_height_m must be positive")
        if self.dwell_s < 0:
            raise ValueError("dwell_s must be non-negative")
        if self.maximum_sample_age_s <= 0:
            raise ValueError("maximum_sample_age_s must be positive")
        self._landed: bool | None = None
        self._land_observed_ns: int | None = None
        self._height_m: float | None = None
        self._position_observed_ns: int | None = None
        self._candidate_since_ns: int | None = None
        self._ready_ns: int | None = None

    @property
    def ready(self) -> bool:
        return self._ready_ns is not None

    @property
    def ready_ns(self) -> int | None:
        return self._ready_ns

    @property
    def height_m(self) -> float | None:
        return self._height_m

    def observe_land(self, *, landed: bool, now_ns: int) -> bool:
        self._landed = landed
        self._land_observed_ns = now_ns
        return self.evaluate(now_ns)

    def observe_local_position(self, *, z_m: float, z_valid: bool, now_ns: int) -> bool:
        self._height_m = -z_m if z_valid else None
        self._position_observed_ns = now_ns
        return self.evaluate(now_ns)

    def evaluate(self, now_ns: int) -> bool:
        if self.ready:
            return True
        maximum_age_ns = int(self.maximum_sample_age_s * 1_000_000_000)
        evidence_is_fresh = (
            self._land_observed_ns is not None
            and self._position_observed_ns is not None
            and 0 <= now_ns - self._land_observed_ns <= maximum_age_ns
            and 0 <= now_ns - self._position_observed_ns <= maximum_age_ns
        )
        conditions_hold = (
            evidence_is_fresh
            and self._landed is False
            and self._height_m is not None
            and self._height_m >= self.minimum_height_m
        )
        if not conditions_hold:
            self._candidate_since_ns = None
            return False
        if self._candidate_since_ns is None:
            self._candidate_since_ns = now_ns
        if now_ns - self._candidate_since_ns >= int(self.dwell_s * 1_000_000_000):
            self._ready_ns = now_ns
            return True
        return False


def physical_takeoff_observed(
    records: Iterable[dict[str, Any]],
    *,
    minimum_height_m: float = MINIMUM_AIRBORNE_HEIGHT_M,
    dwell_s: float = AIRBORNE_DWELL_S,
    maximum_sample_age_s: float = MAXIMUM_SAMPLE_AGE_S,
) -> bool:
    """Replay telemetry through the exact live takeoff predicate."""

    gate = PhysicalTakeoffGate(
        minimum_height_m=minimum_height_m,
        dwell_s=dwell_s,
        maximum_sample_age_s=maximum_sample_age_s,
    )
    ordered = sorted(
        (
            item
            for item in records
            if item.get("kind")
            in {"vehicle_land_detected", "vehicle_local_position"}
            and isinstance(item.get("received_monotonic_ns"), int)
        ),
        key=lambda item: int(item["received_monotonic_ns"]),
    )
    for item in ordered:
        now_ns = int(item["received_monotonic_ns"])
        if item["kind"] == "vehicle_land_detected":
            gate.observe_land(landed=bool(item.get("landed", True)), now_ns=now_ns)
        else:
            gate.observe_local_position(
                z_m=float(item.get("z", 0.0)),
                z_valid=bool(item.get("z_valid", False)),
                now_ns=now_ns,
            )
        if gate.ready:
            return True
    return False
