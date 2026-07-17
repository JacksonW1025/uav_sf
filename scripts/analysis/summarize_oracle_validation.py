#!/usr/bin/env python3
"""Write clause-level live Oracle validation results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    live = json.loads(args.live.read_text(encoding="utf-8"))
    rows = []
    for result in live["results"]:
        for assertion in result["assertions"]:
            rows.append(
                {
                    "case_id": result["case_id"],
                    "mutant_type": result["mutant_type"],
                    "delay_ms": result["delay_ms"],
                    "repeat": result["repeat"],
                    "clause": assertion["clause"],
                    "true_status": assertion["expected"],
                    "predicted_status": assertion["predicted"],
                    "correct": assertion["correct"],
                    "false_positive": assertion["expected"] != "VIOLATION" and assertion["predicted"] == "VIOLATION",
                    "false_negative": assertion["expected"] == "VIOLATION" and assertion["predicted"] != "VIOLATION",
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"live_clause_assertions": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
