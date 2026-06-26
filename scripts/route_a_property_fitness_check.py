#!/usr/bin/env python3
"""ULOG-only Route-A regression for differential property fitness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from property_fitness import differential_property_fitness
from property_oracle import evaluate_ulog, load_thresholds


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = REPO_ROOT / "docs/fuzz1c_decontam_20260625/results.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def strict_pairs(results: dict[str, Any]) -> list[dict[str, Any]]:
    return [pair for pair in results.get("pairs", []) if pair.get("decision") == "STRICT_DIFFERENTIAL"]


def check_route_a(results_path: Path, thresholds_json: Path | None) -> dict[str, Any]:
    thresholds = load_thresholds(thresholds_json)
    results = load_json(results_path)
    records = []
    for pair in strict_pairs(results):
        classical_ulog = REPO_ROOT / pair["classical"]["ulog"]
        mcnn_ulog = REPO_ROOT / pair["mcnn"]["ulog"]
        classical_property = evaluate_ulog(classical_ulog, controller="classical", thresholds=thresholds)
        mcnn_property = evaluate_ulog(mcnn_ulog, controller="mcnn", thresholds=thresholds)
        fitness = differential_property_fitness(
            classical_property,
            mcnn_property,
            target_properties=["P1", "P2"],
        )
        p1p2_flags = [prop for prop in fitness["clean_differential_properties"] if prop in {"P1", "P2"}]
        source_strict = pair.get("decision") == "STRICT_DIFFERENTIAL"
        mcnn_confirmed = bool(mcnn_property.get("controller_identity", {}).get("mcnn_confirmed"))
        raptor_input_present = bool(mcnn_property.get("controller_identity", {}).get("raptor_input_present"))
        records.append(
            {
                "idx": pair.get("idx"),
                "case": pair.get("case"),
                "source_decision": pair.get("decision"),
                "classical_ulog": str(classical_ulog.relative_to(REPO_ROOT)),
                "mcnn_ulog": str(mcnn_ulog.relative_to(REPO_ROOT)),
                "fitness_p1_p2": fitness["fitness"],
                "best_property": fitness["best_property"],
                "clean_differential_properties": fitness["clean_differential_properties"],
                "property_global_strict_s0_vs_s3": fitness["strict_s0_vs_s3"],
                "route_a_decontam_strict": source_strict,
                "mcnn_confirmed": mcnn_confirmed,
                "mcnn_rate_hz": mcnn_property.get("controller_identity", {}).get("neural_control_rate_hz"),
                "raptor_input_present": raptor_input_present,
                "p1_gap": fitness["per_property"]["P1"]["gap"],
                "p2_gap": fitness["per_property"]["P2"]["gap"],
                "p1p2_clean_count": len(p1p2_flags),
                "passed": bool(
                    fitness["fitness"] > 0.0
                    and p1p2_flags
                    and source_strict
                    and mcnn_confirmed
                    and not raptor_input_present
                ),
            }
        )
    return {
        "source": str(results_path.relative_to(REPO_ROOT)),
        "thresholds_json": str(thresholds_json.relative_to(REPO_ROOT)) if thresholds_json else "property_oracle defaults",
        "strict_pair_count": len(records),
        "passed_count": sum(1 for record in records if record["passed"]),
        "passed": bool(records) and all(record["passed"] for record in records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--thresholds-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    summary = check_route_a(args.results.resolve(), args.thresholds_json.resolve() if args.thresholds_json else None)
    if args.output:
        write_json(args.output, summary)
    print(
        json.dumps(
            {
                "passed": summary["passed"],
                "strict_pair_count": summary["strict_pair_count"],
                "passed_count": summary["passed_count"],
                "output": str(args.output) if args.output else None,
            },
            sort_keys=True,
        )
    )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
