#!/usr/bin/env python3
"""Compare one classical and one RAPTOR M1 metrics result."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from property_fitness import differential_property_fitness, property_margins
from property_oracle import PROPERTY_ORDER, evaluate_ulog, load_thresholds


NOISE_FLOOR_DEFAULT = {
    "tracking_error_max_m": 0.05,
    "tracking_error_rms_m": 0.04,
    "final_error_m": 0.05,
    "roll_pitch_max_deg": 1.0,
    "roll_pitch_std_deg": 0.5,
    "angular_rate_max_rad_s": 0.02,
    "angular_rate_std_rad_s": 0.02,
    "motor_saturation_ratio": 0.01,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def metric_delta(raptor: dict[str, Any], classical: dict[str, Any], key: str) -> float | None:
    rv = raptor.get(key)
    cv = classical.get(key)
    if rv is None or cv is None:
        return None
    return float(rv) - float(cv)


def trace_array(metrics: dict[str, Any], key: str) -> np.ndarray:
    trace = metrics.get(key) or []
    if not trace:
        return np.empty((0, 4), dtype=float)
    return np.asarray(trace, dtype=float)


def time_to_divergence(classical: dict[str, Any], raptor: dict[str, Any], threshold_m: float) -> float | None:
    a = trace_array(classical, "position_trace")
    b = trace_array(raptor, "position_trace")
    if len(a) < 2 or len(b) < 2:
        return None
    start = max(float(a[0, 0]), float(b[0, 0]))
    end = min(float(a[-1, 0]), float(b[-1, 0]))
    if end <= start:
        return None
    times = np.linspace(start, end, max(2, int((end - start) * 20)))
    apos = np.column_stack([np.interp(times, a[:, 0], a[:, i]) for i in range(1, 4)])
    bpos = np.column_stack([np.interp(times, b[:, 0], b[:, i]) for i in range(1, 4)])
    dist = np.linalg.norm(apos - bpos, axis=1)
    idx = np.where(dist > threshold_m)[0]
    if len(idx) == 0:
        return None
    return float(times[int(idx[0])] - start)


def quadrant(classical_safe: bool, raptor_safe: bool) -> str:
    if classical_safe and raptor_safe:
        return "boring_both_safe"
    if not classical_safe and raptor_safe:
        return "interesting_not_bug"
    if classical_safe and not raptor_safe:
        return "primary_bug"
    return "too_hard_not_bug"


def property_severity_value(result: dict[str, Any]) -> int | None:
    severity = result.get("severity", {})
    value = severity.get("severity") if isinstance(severity, dict) else None
    return int(value) if isinstance(value, int) else None


def property_severity_label(result: dict[str, Any]) -> str | None:
    severity = result.get("severity", {})
    label = severity.get("label") if isinstance(severity, dict) else None
    return str(label) if label is not None else None


def property_differential(
    classical_property: dict[str, Any],
    neural_property: dict[str, Any],
    margin_c: float | dict[str, float] | None = None,
) -> dict[str, Any]:
    explicit = None
    if isinstance(margin_c, dict):
        explicit = {str(key): float(value) for key, value in margin_c.items() if isinstance(value, (int, float))}
    elif isinstance(margin_c, (int, float)):
        explicit = {prop: float(margin_c) for prop in PROPERTY_ORDER}
    margins = property_margins(classical_property, neural_property, explicit)
    fitness = differential_property_fitness(
        classical_property,
        neural_property,
        target_properties=PROPERTY_ORDER,
        explicit_margins=margins,
    )
    per_property: dict[str, Any] = {}
    clean = []
    for prop in PROPERTY_ORDER:
        item = dict(fitness["per_property"][prop])
        per_property[prop] = item
        if item["clean_differential"]:
            clean.append(prop)

    csev = fitness["classical_severity"]
    nsev = fitness["neural_severity"]
    if csev is None or nsev is None:
        strict = False
        wide = False
    else:
        strict = csev == 0 and nsev >= 3
        wide = csev <= 2 and nsev >= 3

    return {
        "classical_severity": csev,
        "classical_severity_label": property_severity_label(classical_property),
        "neural_severity": nsev,
        "neural_severity_label": property_severity_label(neural_property),
        "candidate_differential_properties": fitness["candidate_differential_properties"],
        "clean_differential_properties": clean,
        "rho_jitter_reproduction_margins": fitness["rho_jitter_reproduction_margins"],
        "property_finding": bool(clean),
        "per_property": per_property,
        "strict_s0_vs_s3": bool(strict),
        "wide_control_vs_uncontrolled": bool(wide),
        "catastrophic_property_primary_bug": bool(clean and wide),
        "property_primary_bug": bool(clean),
        "fitness_validation": fitness,
    }


def noise_floor(theta: dict[str, Any], classical: dict[str, Any], raptor: dict[str, Any]) -> dict[str, float]:
    floor = dict(NOISE_FLOOR_DEFAULT)
    for source in [theta.get("noise_floor", {}), classical.get("noise_floor", {}), raptor.get("noise_floor", {})]:
        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(value, (int, float)):
                    floor[key] = float(value)
    return floor


def effective_deltas(deltas: dict[str, float | None], floor: dict[str, float]) -> dict[str, float | None]:
    effective: dict[str, float | None] = {}
    for key, value in deltas.items():
        if value is None:
            effective[key] = None
            continue
        effective[key] = max(0.0, float(value) - float(floor.get(key, 0.0)))
    return effective


def divergence_quality(
    effective: dict[str, float | None],
    time_to_divergence_s: float | None,
    classical: dict[str, Any],
    raptor: dict[str, Any],
) -> float:
    weights = {
        "tracking_error_max_m": 1.0,
        "tracking_error_rms_m": 3.0,
        "final_error_m": 1.5,
        "roll_pitch_max_deg": 0.08,
        "roll_pitch_std_deg": 0.12,
        "angular_rate_max_rad_s": 0.6,
        "angular_rate_std_rad_s": 0.8,
        "motor_saturation_ratio": 6.0,
    }
    score = 0.0
    for key, weight in weights.items():
        value = effective.get(key)
        if value is not None:
            score += weight * max(0.0, float(value))
    if time_to_divergence_s is not None:
        score += 2.0 / (1.0 + max(0.0, float(time_to_divergence_s)))
    thresholds = raptor.get("safe_thresholds", {}) or classical.get("safe_thresholds", {})
    for key in ["tracking_error_max_m", "roll_pitch_max_deg", "angular_rate_max_rad_s", "motor_saturation_ratio"]:
        rvalue = raptor.get(key)
        limit_key = "motor_saturation_ratio_max" if key == "motor_saturation_ratio" else key
        limit = thresholds.get(limit_key)
        if rvalue is not None and limit:
            score += 0.5 * max(0.0, float(rvalue) / float(limit) - 0.75)
    if not bool(raptor.get("safe")):
        score += 20.0
    return float(score)


def compare(
    theta: dict[str, Any],
    classical: dict[str, Any],
    raptor: dict[str, Any],
    classical_property: dict[str, Any] | None = None,
    raptor_property: dict[str, Any] | None = None,
) -> dict[str, Any]:
    div_threshold = float(theta.get("divergence_thresholds", {}).get("position_divergence_m", 2.0))
    ttd = time_to_divergence(classical, raptor, div_threshold)
    deltas = {
        "tracking_error_max_m": metric_delta(raptor, classical, "tracking_error_max_m"),
        "tracking_error_rms_m": metric_delta(raptor, classical, "tracking_error_rms_m"),
        "final_error_m": metric_delta(raptor, classical, "final_error_m"),
        "roll_pitch_max_deg": metric_delta(raptor, classical, "roll_pitch_max_deg"),
        "roll_pitch_std_deg": metric_delta(raptor, classical, "roll_pitch_std_deg"),
        "angular_rate_max_rad_s": metric_delta(raptor, classical, "angular_rate_max_rad_s"),
        "angular_rate_std_rad_s": metric_delta(raptor, classical, "angular_rate_std_rad_s"),
        "motor_saturation_ratio": metric_delta(raptor, classical, "motor_saturation_ratio"),
    }
    floor = noise_floor(theta, classical, raptor)
    effective = effective_deltas(deltas, floor)
    classical_usable = bool(classical.get("safe")) and not bool(classical.get("infrastructure_limited"))
    raptor_safe = bool(raptor.get("safe"))
    result = {
        "tag": theta.get("tag"),
        "theta": theta,
        "classical": classical,
        "raptor": raptor,
        "quadrant": quadrant(classical_usable, raptor_safe),
        "classical_usable_for_primary": classical_usable,
        "primary_bug": classical_usable and not raptor_safe and divergence_quality(effective, ttd, classical, raptor) > 0.0,
        "divergence": {
            "deltas_raptor_minus_classical": deltas,
            "effective_deltas_above_noise_floor": effective,
            "noise_floor": floor,
            "quality": divergence_quality(effective, ttd, classical, raptor) if classical_usable else 0.0,
            "position_divergence_threshold_m": div_threshold,
            "time_to_divergence_s": ttd,
            "stability_margin_proxy": {
                "classical_angular_rate_peak_rad_s": classical.get("angular_rate_max_rad_s"),
                "raptor_angular_rate_peak_rad_s": raptor.get("angular_rate_max_rad_s"),
                "classical_roll_pitch_max_deg": classical.get("roll_pitch_max_deg"),
                "raptor_roll_pitch_max_deg": raptor.get("roll_pitch_max_deg"),
            },
        },
    }
    if classical_property is not None and raptor_property is not None:
        result["property_oracle"] = {
            "classical": classical_property,
            "neural": raptor_property,
            "differential": property_differential(classical_property, raptor_property),
        }
    return result


def property_only_result(
    theta: dict[str, Any],
    classical_property: dict[str, Any],
    neural_property: dict[str, Any],
) -> dict[str, Any]:
    differential = property_differential(classical_property, neural_property)
    return {
        "tag": theta.get("tag"),
        "theta": theta,
        "quadrant": "property_only",
        "primary_bug": bool(differential["property_primary_bug"]),
        "classical_usable_for_primary": differential["classical_severity"] == 0,
        "property_oracle": {
            "classical": classical_property,
            "neural": neural_property,
            "differential": differential,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theta", type=Path)
    parser.add_argument("--classical", type=Path)
    parser.add_argument("--raptor", "--neural", dest="raptor", type=Path)
    parser.add_argument("--classical-property", type=Path)
    parser.add_argument("--raptor-property", "--neural-property", dest="raptor_property", type=Path)
    parser.add_argument("--classical-ulog", type=Path)
    parser.add_argument("--raptor-ulog", "--neural-ulog", dest="raptor_ulog", type=Path)
    parser.add_argument("--neural-controller", choices=["raptor", "mcnn"], default="raptor")
    parser.add_argument("--thresholds-json", type=Path)
    parser.add_argument("--classical-analysis-start-us", type=int)
    parser.add_argument("--classical-analysis-end-us", type=int)
    parser.add_argument("--raptor-analysis-start-us", "--neural-analysis-start-us", dest="raptor_analysis_start_us", type=int)
    parser.add_argument("--raptor-analysis-end-us", "--neural-analysis-end-us", dest="raptor_analysis_end_us", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    theta = load_json(args.theta) if args.theta else {}
    thresholds = load_thresholds(args.thresholds_json)

    classical_property = load_json(args.classical_property) if args.classical_property else None
    raptor_property = load_json(args.raptor_property) if args.raptor_property else None
    if classical_property is None and args.classical_ulog:
        classical_property = evaluate_ulog(
            args.classical_ulog,
            controller="classical",
            theta=theta,
            thresholds=thresholds,
            analysis_start_us=args.classical_analysis_start_us,
            analysis_end_us=args.classical_analysis_end_us,
        )
    if raptor_property is None and args.raptor_ulog:
        raptor_property = evaluate_ulog(
            args.raptor_ulog,
            controller=args.neural_controller,
            theta=theta,
            thresholds=thresholds,
            analysis_start_us=args.raptor_analysis_start_us,
            analysis_end_us=args.raptor_analysis_end_us,
        )

    if args.classical and args.raptor:
        result = compare(
            theta,
            load_json(args.classical),
            load_json(args.raptor),
            classical_property,
            raptor_property,
        )
    elif classical_property is not None and raptor_property is not None:
        result = property_only_result(theta, classical_property, raptor_property)
    else:
        raise SystemExit("provide either --classical/--raptor metrics, or property JSONs/ULOGs for both controllers")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "quadrant": result["quadrant"],
                "primary_bug": result["primary_bug"],
                "property": result.get("property_oracle", {}).get("differential"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
