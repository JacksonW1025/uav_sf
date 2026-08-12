#!/usr/bin/env python3
"""Fit and apply an uncertainty-bounded piecewise clock bridge."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
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
    knots: tuple[tuple[int, int], ...]

    def map(self, source_ns: int) -> int:
        if not self.valid_from_ns <= source_ns <= self.valid_until_ns:
            raise ClockBridgeError("timestamp is outside the bridge validity interval")
        sources = [item[0] for item in self.knots]
        right = min(bisect_right(sources, source_ns), len(self.knots) - 1)
        left = max(0, right - 1)
        x0, y0 = self.knots[left]
        x1, y1 = self.knots[right]
        if x0 == x1:
            return y0
        return int(round(y0 + (source_ns - x0) * (y1 - y0) / (x1 - x0)))

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
    if any(right <= left for left, right in zip(analysis, analysis[1:])):
        raise ClockBridgeError("analysis timestamps must be strictly increasing")
    x0 = source[len(source) // 2]
    y0 = analysis[len(analysis) // 2]
    rate = (analysis[-1] - analysis[0]) / (source[-1] - source[0])
    if rate <= 0:
        raise ClockBridgeError("clock rate must be positive")
    # Lockstep simulation does not advance at one globally constant wall-clock
    # rate. Predict each interior knot from its neighbours to bound local
    # interpolation error, then retain all samples as piecewise-linear knots.
    residuals = []
    for index in range(1, len(source) - 1):
        predicted = analysis[index - 1] + (
            (source[index] - source[index - 1])
            * (analysis[index + 1] - analysis[index - 1])
            / (source[index + 1] - source[index - 1])
        )
        residuals.append(abs(analysis[index] - int(round(predicted))))
    half_round_trip = max(int(sample.get("round_trip_ns", 0)) for sample in ordered) // 2
    uncertainty = max(residuals, default=0) + half_round_trip
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
        knots=tuple(zip(source, analysis)),
    )
