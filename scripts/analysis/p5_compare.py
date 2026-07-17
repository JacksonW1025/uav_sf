#!/usr/bin/env python3
"""Compute preregistered paired P5 mechanism differences with uncertainty."""

from __future__ import annotations

import argparse
import csv
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
                    "effect_direction": "dynamic_higher" if median > 0 else "dynamic_lower" if median < 0 else "no_shift",
                    "interpretation": "measurable mechanism difference" if measurable else "not resolved above uncertainty",
                }
            )
    return {
        "schema_version": "1.0",
        "input_row_count": len(rows),
        "valid_row_count": len(valid),
        "complete_pair_count": len(complete),
        "invalid_or_environment_rows_excluded": len(rows) - len(valid),
        "comparison_count": len(result_rows),
        "global_safety_ranking": "NOT_PERMITTED",
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
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    config = yaml.safe_load(args.analysis.read_text(encoding="utf-8"))
    result = compare(rows, config)
    args.paired_output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "cell_id", "metric", "valid_pair_count", "median_dynamic_minus_offboard",
        "iqr", "bootstrap_ci_lower", "bootstrap_ci_upper", "combined_uncertainty",
        "effect_direction", "interpretation",
    ]
    with args.paired_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(result["comparisons"])
    args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("complete_pair_count", "comparison_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
