#!/usr/bin/env python3
"""Fit and apply an uncertainty-bounded affine clock bridge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable


class ClockBridgeError(ValueError):
    """Clock evidence is insufficient for a valid mapping."""


@dataclass(frozen=True)
class ClockBridge:
    bridge_id: str
    source_domain: str
    reference_source_ns: int
    reference_analysis_ns: int
    rate_ratio: float
    uncertainty_ns: int
    valid_from_ns: int
    valid_until_ns: int
    sample_count: int

    def map(self, source_ns: int) -> int:
        if not self.valid_from_ns <= source_ns <= self.valid_until_ns:
            raise ClockBridgeError("timestamp is outside the bridge validity interval")
        return int(
            round(
                self.reference_analysis_ns
                + (source_ns - self.reference_source_ns) * self.rate_ratio
            )
        )

    def event(self, *, run_id: str, sequence: int, timestamp_ns: int) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "sequence": sequence,
            "kind": "clock_bridge",
            "timestamp_ns": timestamp_ns,
            "source_domain": "analysis_monotonic",
            "bridge": self.__dict__,
        }


def fit_clock_bridge(
    samples: Iterable[dict[str, int | str]], *, maximum_uncertainty_ns: int
) -> ClockBridge:
    values = list(samples)
    if len(values) < 5:
        raise ClockBridgeError("at least five clock samples are required")
    domains = {str(sample["source_domain"]) for sample in values}
    if len(domains) != 1:
        raise ClockBridgeError("clock samples must use one source domain")
    ordered = sorted(values, key=lambda sample: int(sample["source_ns"]))
    source = [int(sample["source_ns"]) for sample in ordered]
    analysis = [int(sample["analysis_ns"]) for sample in ordered]
    if any(right <= left for left, right in zip(source, source[1:])):
        raise ClockBridgeError("source timestamps must be strictly increasing")
    x0 = source[len(source) // 2]
    y0 = analysis[len(analysis) // 2]
    centered_x = [value - x0 for value in source]
    centered_y = [value - y0 for value in analysis]
    denominator = sum(value * value for value in centered_x)
    if denominator == 0:
        raise ClockBridgeError("clock samples have no time span")
    rate = sum(x * y for x, y in zip(centered_x, centered_y)) / denominator
    if rate <= 0:
        raise ClockBridgeError("clock rate must be positive")
    residuals = [
        abs(y - int(round(y0 + (x - x0) * rate)))
        for x, y in zip(source, analysis)
    ]
    half_round_trip = max(int(sample.get("round_trip_ns", 0)) for sample in ordered) // 2
    uncertainty = max(residuals) + half_round_trip
    if uncertainty > maximum_uncertainty_ns:
        raise ClockBridgeError("clock uncertainty exceeds the configured bound")
    material = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return ClockBridge(
        bridge_id="clock-" + hashlib.sha256(material).hexdigest()[:16],
        source_domain=domains.pop(),
        reference_source_ns=x0,
        reference_analysis_ns=y0,
        rate_ratio=rate,
        uncertainty_ns=uncertainty,
        valid_from_ns=source[0],
        valid_until_ns=source[-1],
        sample_count=len(ordered),
    )
