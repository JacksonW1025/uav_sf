#!/usr/bin/env python3
"""Validate and materialize the preregistered P5 paired execution plan."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = ROOT / "experiments" / "probes" / "p5" / "scenario_matrix.yaml"


def load_matrix(path: Path = DEFAULT_MATRIX) -> dict:
    matrix = yaml.safe_load(path.read_text(encoding="utf-8"))
    classes = [cell["transition_class"] for cell in matrix["cells"]]
    if classes != [f"T{index}" for index in range(1, 10)]:
        raise ValueError("P5 core matrix must contain T1 through T9 exactly once")
    if int(matrix["paired_repeats"]) < 5:
        raise ValueError("P5 requires at least five initial paired repeats")
    if set(matrix["mechanisms"]) != {"legacy_offboard", "dynamic_external_mode"}:
        raise ValueError("P5 requires both route mechanisms")
    return matrix


def execution_plan(matrix: dict) -> list[dict]:
    rows: list[dict] = []
    for cell_index, cell in enumerate(matrix["cells"], start=1):
        for repeat in range(1, int(matrix["paired_repeats"]) + 1):
            pair_id = f"{cell['cell_id']}_pair_r{repeat}"
            seed = 50_000 + cell_index * 100 + repeat
            for mechanism in matrix["mechanisms"]:
                rows.append(
                    {
                        "run_id": f"{pair_id}_{mechanism}",
                        "pair_id": pair_id,
                        "cell_id": cell["cell_id"],
                        "transition_class": cell["transition_class"],
                        "context": cell["context"],
                        "action": cell["action"],
                        "mechanism": mechanism,
                        "simulation_seed": seed,
                        "repeat": repeat,
                        "fault_offset_s": matrix["locked_execution"]["fault_offset_s"],
                        "fallback_mode": matrix["locked_execution"]["fallback_mode"],
                        "status": "PLANNED",
                    }
                )
    return rows


def write_plan(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runs" / "p5" / "execution_plan.tsv"
    )
    args = parser.parse_args()
    matrix = load_matrix(args.matrix)
    rows = execution_plan(matrix)
    write_plan(rows, args.output)
    print(json.dumps({"paired_cells": len(matrix["cells"]), "planned_runs": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
