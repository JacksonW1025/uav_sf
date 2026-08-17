"""Pure helpers for the bounded Stage A2 straight-line workload."""

from __future__ import annotations


def straight_line_target(
    elapsed_s: float, *, settle_s: float, speed_m_s: float, distance_m: float
) -> float:
    if min(settle_s, speed_m_s, distance_m) < 0:
        raise ValueError("moving workload parameters must be non-negative")
    return min(distance_m, max(0.0, elapsed_s - settle_s) * speed_m_s)


def progress_from_origin(current_x_m: float, origin_x_m: float) -> float:
    return max(0.0, current_x_m - origin_x_m)
