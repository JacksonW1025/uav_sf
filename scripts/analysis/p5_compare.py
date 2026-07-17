#!/usr/bin/env python3
"""Compute preregistered paired P5 mechanism differences with uncertainty."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = ROOT / "experiments" / "probes" / "p5" / "pre_registered_analysis.yaml"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return quartiles[2] - quartiles[0]


def _bootstrap_median(values: list[float], *, samples: int, seed: int = 5503) -> list[float]:
    generator = random.Random(seed)
    estimates = sorted(
        statistics.median(generator.choices(values, k=len(values))) for _ in range(samples)
    )
    return [
        estimates[int(0.025 * (len(estimates) - 1))],
        estimates[int(0.975 * (len(estimates) - 1))],
    ]


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    spread = statistics.stdev(values)
    if math.isclose(mean, 0.0, abs_tol=1e-12):
        return None if spread > 0.0 else 0.0
    return spread / abs(mean)


def compare(rows: list[dict[str, str]], config: dict[str, Any]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("validity") == "VALID"]
    paired: dict[str, dict[str, dict[str, str]]] = {}
    for row in valid:
        paired.setdefault(row["pair_id"], {})[row["mechanism"]] = row
    complete = {
        pair_id: mechanisms
        for pair_id, mechanisms in paired.items()
        if set(mechanisms) == {"legacy_offboard", "dynamic_external_mode"}
    }
    result_rows: list[dict[str, Any]] = []
    adaptive_cells: dict[str, set[str]] = {}
    for metric in config["metrics"]:
        by_cell: dict[str, list[tuple[float, float]]] = {}
        for mechanisms in complete.values():
            legacy = mechanisms["legacy_offboard"]
            dynamic = mechanisms["dynamic_external_mode"]
            left = _number(legacy.get(metric))
            right = _number(dynamic.get(metric))
            if left is None or right is None:
                continue
            left_u = _number(legacy.get(f"{metric}_uncertainty")) or 0.0
            right_u = _number(dynamic.get(f"{metric}_uncertainty")) or 0.0
            by_cell.setdefault(legacy["cell_id"], []).append(
                (right - left, math.hypot(left_u, right_u))
            )
        for cell_id, observations in sorted(by_cell.items()):
            differences = [item[0] for item in observations]
            uncertainty = max(item[1] for item in observations)
            median = statistics.median(differences)
            coefficient_of_variation = _coefficient_of_variation(differences)
            cv_trigger = coefficient_of_variation is None or coefficient_of_variation > float(
                config["adaptation"]["increase_when_coefficient_of_variation_exceeds"]
            )
            uncertainty_trigger = (
                bool(config["adaptation"]["increase_when_difference_below_combined_uncertainty"])
                and abs(median) < uncertainty
            )
            trigger_reasons = []
            if cv_trigger:
                trigger_reasons.append("coefficient_of_variation")
            if uncertainty_trigger:
                trigger_reasons.append("difference_below_combined_uncertainty")
            if trigger_reasons:
                adaptive_cells.setdefault(cell_id, set()).update(trigger_reasons)
            ci = _bootstrap_median(
                differences,
                samples=int(config["confidence_interval"]["resamples"]),
            )
            measurable = (
                abs(median) > uncertainty
                and (ci[0] > uncertainty or ci[1] < -uncertainty)
            )
            result_rows.append(
                {
                    "cell_id": cell_id,
                    "metric": metric,
                    "valid_pair_count": len(differences),
                    "median_dynamic_minus_offboard": median,
                    "iqr": _iqr(differences),
                    "bootstrap_ci_lower": ci[0],
                    "bootstrap_ci_upper": ci[1],
                    "combined_uncertainty": uncertainty,
                    "coefficient_of_variation": coefficient_of_variation,
                    "difference_below_combined_uncertainty": uncertainty_trigger,
                    "adaptive_repeat_trigger": bool(trigger_reasons),
                    "adaptive_repeat_reasons": ",".join(trigger_reasons),
                    "effect_direction": "dynamic_higher" if median > 0 else "dynamic_lower" if median < 0 else "no_shift",
                    "interpretation": "measurable mechanism difference" if measurable else "not resolved above uncertainty",
                }
            )
    adaptive_decision = {
        "schema_version": "1.0",
        "initial_paired_repeats": int(config["adaptation"]["initial_paired_repeats"]),
        "maximum_paired_repeats": int(config["adaptation"]["maximum_paired_repeats"]),
        "initial_complete_pair_count": len(complete),
        "triggered_cells": [
            {"cell_id": cell_id, "reasons": sorted(reasons)}
            for cell_id, reasons in sorted(adaptive_cells.items())
        ],
        "decision": "INCREASE_TRIGGERED_CELLS_TO_MAXIMUM",
    }
    return {
        "schema_version": "1.0",
        "input_row_count": len(rows),
        "valid_row_count": len(valid),
        "complete_pair_count": len(complete),
        "invalid_or_environment_rows_excluded": len(rows) - len(valid),
        "comparison_count": len(result_rows),
        "global_safety_ranking": "NOT_PERMITTED",
        "adaptive_repeat_decision": adaptive_decision,
        "comparisons": result_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--paired-output", type=Path, default=ROOT / "data" / "processed" / "p5" / "paired_results.tsv"
    )
    parser.add_argument(
        "--summary", type=Path, default=ROOT / "data" / "processed" / "p5" / "summary.json"
    )
    parser.add_argument("--analysis", type=Path, default=ANALYSIS)
    parser.add_argument("--adaptive-decision", type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    config = yaml.safe_load(args.analysis.read_text(encoding="utf-8"))
    result = compare(rows, config)
    result["adaptive_repeat_decision"].update(
        {
            "input_results": str(args.input.resolve().relative_to(ROOT)),
            "input_results_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
            "analysis_config": str(args.analysis.resolve().relative_to(ROOT)),
            "analysis_config_sha256": hashlib.sha256(args.analysis.read_bytes()).hexdigest(),
        }
    )
    args.paired_output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "cell_id", "metric", "valid_pair_count", "median_dynamic_minus_offboard",
        "iqr", "bootstrap_ci_lower", "bootstrap_ci_upper", "combined_uncertainty",
        "coefficient_of_variation", "difference_below_combined_uncertainty",
        "adaptive_repeat_trigger", "adaptive_repeat_reasons",
        "effect_direction", "interpretation",
    ]
    with args.paired_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(result["comparisons"])
    args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.adaptive_decision is not None:
        args.adaptive_decision.parent.mkdir(parents=True, exist_ok=True)
        args.adaptive_decision.write_text(
            json.dumps(result["adaptive_repeat_decision"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({key: result[key] for key in ("complete_pair_count", "comparison_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
