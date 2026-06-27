#!/usr/bin/env python3
"""Differential property-oracle fitness for Tier 0.5 search.

The property oracle computes per-controller robustness values rho_i. This
module turns a paired classical/neural result into a search signal:
classical-safe per-property gaps, not absolute neural rho.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable

from property_oracle import PROPERTY_ORDER
from validity_automation import reproduction_margins, robust_property_finding, robust_violation_margin


FITNESS_FLOOR = -1.0e9

DEFAULT_PROPERTY_MARGINS: dict[str, float] = {
    # 30% of the recomputed classical nominal minimum margins, except P5 which
    # uses the non-vacuous pure-step calibration classical minimum.
    "P1": 0.4548139946,
    "P2": 2.3421337853,
    "P3": 0.1500000000,
    "P4": 0.2023303610,
    "P5": 0.1083387278,
    "P6": 0.0759150636,
    "P7": 0.1126242187,
}

DEFAULT_SEARCH_TARGET_PROPERTIES = ("P4", "P6", "P7")
STEP_SEARCH_TARGET_PROPERTIES = ("P4", "P5", "P6", "P7")
VALIDATION_PROPERTIES = ("P1", "P2", "P4", "P5", "P6", "P7")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _threshold_sources(
    classical_property: dict[str, Any],
    neural_property: dict[str, Any],
) -> list[dict[str, Any]]:
    sources = []
    for result in (classical_property, neural_property):
        thresholds = result.get("thresholds")
        if isinstance(thresholds, dict):
            sources.append(thresholds)
    return sources


def property_margins(
    classical_property: dict[str, Any],
    neural_property: dict[str, Any],
    explicit_margins: dict[str, float] | None = None,
) -> dict[str, float]:
    margins = dict(DEFAULT_PROPERTY_MARGINS)
    for thresholds in _threshold_sources(classical_property, neural_property):
        by_property = thresholds.get("margin_c_by_property")
        if isinstance(by_property, dict):
            for prop, value in by_property.items():
                if prop in PROPERTY_ORDER and isinstance(value, (int, float)):
                    margins[prop] = float(value)
        for prop in PROPERTY_ORDER:
            key = f"margin_c_{prop}"
            value = thresholds.get(key)
            if isinstance(value, (int, float)):
                margins[prop] = float(value)
    if explicit_margins:
        for prop, value in explicit_margins.items():
            if prop in PROPERTY_ORDER:
                margins[prop] = float(value)
    return margins


def _finite_number(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def _detail_for(result: dict[str, Any], prop: str) -> dict[str, Any]:
    details = result.get("details")
    if not isinstance(details, dict):
        return {}
    detail = details.get(prop)
    return detail if isinstance(detail, dict) else {}


def property_is_vacuous(classical_property: dict[str, Any], neural_property: dict[str, Any], prop: str) -> bool:
    c_detail = _detail_for(classical_property, prop)
    n_detail = _detail_for(neural_property, prop)
    return bool(c_detail.get("vacuous")) or bool(n_detail.get("vacuous"))


def severity_value(result: dict[str, Any]) -> int | None:
    severity = result.get("severity", {})
    value = severity.get("severity") if isinstance(severity, dict) else None
    return int(value) if isinstance(value, int) else None


def severity_label(result: dict[str, Any]) -> str | None:
    severity = result.get("severity", {})
    label = severity.get("label") if isinstance(severity, dict) else None
    return str(label) if label is not None else None


def normalize_target_properties(target_properties: Iterable[str] | None) -> list[str]:
    if target_properties is None:
        target_properties = VALIDATION_PROPERTIES
    out = []
    for prop in target_properties:
        if prop not in PROPERTY_ORDER:
            raise ValueError(f"unknown property {prop!r}; expected one of {PROPERTY_ORDER}")
        if prop not in out:
            out.append(prop)
    return out


def theta_has_nonvacuous_step(theta: dict[str, Any]) -> bool:
    setpoint = theta.get("setpoint", {}) if isinstance(theta, dict) else {}
    theta_genome = theta.get("theta_genome", {}) if isinstance(theta, dict) else {}
    map_elites = theta_genome.get("map_elites", {}) if isinstance(theta_genome, dict) else {}
    if map_elites.get("disturbance_type") == "step":
        return True
    if setpoint.get("type") != "step":
        return False
    step = setpoint.get("step", {})
    if not isinstance(step, dict):
        return False
    delta = step.get("delta_ned", [0.0, 0.0, 0.0])
    if not isinstance(delta, list) or len(delta) != 3:
        return False
    try:
        norm = math.sqrt(sum(float(value) * float(value) for value in delta))
    except (TypeError, ValueError):
        return False
    return norm >= 0.5


def driver_target_properties(theta: dict[str, Any]) -> list[str]:
    if theta_has_nonvacuous_step(theta):
        return list(STEP_SEARCH_TARGET_PROPERTIES)
    return list(DEFAULT_SEARCH_TARGET_PROPERTIES)


def differential_property_fitness(
    classical_property: dict[str, Any],
    neural_property: dict[str, Any],
    *,
    target_properties: Iterable[str] | None = None,
    explicit_margins: dict[str, float] | None = None,
    explicit_reproduction_margins: dict[str, float] | None = None,
) -> dict[str, Any]:
    targets = normalize_target_properties(target_properties)
    margins = property_margins(classical_property, neural_property, explicit_margins)
    repro_margins = reproduction_margins()
    if explicit_reproduction_margins:
        for prop, value in explicit_reproduction_margins.items():
            if prop in PROPERTY_ORDER:
                repro_margins[prop] = float(value)
    classical_rho = classical_property.get("rho", {})
    neural_rho = neural_property.get("rho", {})
    if not isinstance(classical_rho, dict) or not isinstance(neural_rho, dict):
        raise ValueError("property results must contain rho objects")

    per_property: dict[str, Any] = {}
    clean: list[str] = []
    candidates: list[str] = []
    valid_gaps: list[tuple[str, float]] = []

    for prop in PROPERTY_ORDER:
        c = _finite_number(classical_rho.get(prop))
        n = _finite_number(neural_rho.get(prop))
        margin = float(margins[prop])
        repro_margin = float(repro_margins[prop])
        target = prop in targets
        vacuous = property_is_vacuous(classical_property, neural_property, prop)
        available = c is not None and n is not None
        classical_margin_valid = bool(available and c is not None and c >= margin)
        candidate_differential = bool(available and not vacuous and n is not None and n <= 0.0 and classical_margin_valid)
        clean_differential = robust_property_finding(
            c,
            n,
            margin,
            repro_margin,
            vacuous=vacuous,
        )
        gap = (c - n) if available and c is not None and n is not None else None
        valid_for_fitness = bool(target and available and not vacuous and classical_margin_valid)

        reason = None
        if not available:
            reason = "missing_or_nonfinite_rho"
        elif vacuous:
            reason = "vacuous_property"
        elif not classical_margin_valid:
            reason = "classical_below_property_margin"
        elif not target:
            reason = "not_in_target_set"

        record = {
            "available": available,
            "target": target,
            "vacuous": vacuous,
            "classical_rho": c,
            "neural_rho": n,
            "margin_c": margin,
            "rho_jitter_reproduction_margin": repro_margin,
            "neural_violation_margin": robust_violation_margin(n),
            "classical_margin_valid": classical_margin_valid,
            "gap": gap,
            "valid_for_fitness": valid_for_fitness,
            "candidate_differential": candidate_differential,
            "clean_differential": clean_differential,
        }
        if reason:
            record["excluded_reason"] = reason
        per_property[prop] = record
        if candidate_differential:
            candidates.append(prop)
        if clean_differential:
            clean.append(prop)
        if valid_for_fitness and gap is not None:
            valid_gaps.append((prop, float(gap)))

    if valid_gaps:
        best_property, fitness = max(valid_gaps, key=lambda item: item[1])
    else:
        best_property, fitness = None, FITNESS_FLOOR

    csev = severity_value(classical_property)
    nsev = severity_value(neural_property)
    strict = bool(csev == 0 and nsev is not None and nsev >= 3)
    wide = bool(csev is not None and csev <= 2 and nsev is not None and nsev >= 3)
    return {
        "fitness": float(fitness),
        "fitness_floor": FITNESS_FLOOR,
        "fitness_semantics": "max(classical_rho - neural_rho) over target properties with classical_rho >= per-property margin_c",
        "best_property": best_property,
        "target_properties": targets,
        "valid_property_count": len(valid_gaps),
        "candidate_differential_properties": candidates,
        "clean_differential_properties": clean,
        "rho_jitter_reproduction_margins": repro_margins,
        "property_finding": bool(clean),
        "classical_severity": csev,
        "classical_severity_label": severity_label(classical_property),
        "neural_severity": nsev,
        "neural_severity_label": severity_label(neural_property),
        "strict_s0_vs_s3": strict,
        "wide_control_vs_uncontrolled": wide,
        "per_property": per_property,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classical-property", type=Path, required=True)
    parser.add_argument("--neural-property", type=Path, required=True)
    parser.add_argument("--target-properties", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    targets = [item.strip() for item in args.target_properties.split(",") if item.strip()] or None
    result = differential_property_fitness(
        load_json(args.classical_property),
        load_json(args.neural_property),
        target_properties=targets,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    print(
        json.dumps(
            {
                "fitness": result["fitness"],
                "best_property": result["best_property"],
                "targets": result["target_properties"],
                "clean_differential_properties": result["clean_differential_properties"],
                "output": str(args.output) if args.output else None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
