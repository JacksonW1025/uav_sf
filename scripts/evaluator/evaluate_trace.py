#!/usr/bin/env python3
"""Evaluate one closed trace through the Evidence Gate and all contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.evaluator.plan import PlanError, load_plan
from scripts.evaluator.result_model import enrich_evaluation, write_evaluation
from scripts.evaluator.sequence_obligations import (
    SequenceObligationError,
    resolve_obligations,
)
from scripts.model.runtime_route import RouteModelError, read_trace
from scripts.oracles.evidence_gate import evaluate_evidence
from scripts.oracles.freshness_lineage import evaluate_freshness_lineage
from scripts.oracles.registration_contract import evaluate_registration_contract
from scripts.oracles.route_conformance import evaluate_route_conformance
from scripts.oracles.successor_progression import evaluate_successor_progression


def evaluate(events: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    # An episode that can carry more than one sequence preregisters the
    # obligations of each and the trace-decided condition that selects between
    # them.  The branch is chosen once, here, so the Gate and every Oracle are
    # run against one resolved set of obligations rather than deciding for
    # themselves.  Resolving before the Gate is safe: the condition is decided
    # from trace events alone, and evidence too thin to establish it makes it
    # false, which selects the branch that demands more.
    resolved, resolution = resolve_obligations(events, plan)
    gate = evaluate_evidence(events, resolved)
    oracle_results = [
        evaluate_route_conformance(events, resolved),
        evaluate_freshness_lineage(events, resolved),
        evaluate_successor_progression(events, resolved),
        evaluate_registration_contract(events, resolved),
    ]
    statuses = [
        clause["status"]
        for result in oracle_results
        for clause in result["clauses"].values()
    ]
    if gate["status"] != "ADMISSIBLE":
        overall = "INCONCLUSIVE"
    elif "VIOLATION" in statuses:
        overall = "VIOLATION"
    elif "UNKNOWN" in statuses:
        overall = "INCONCLUSIVE"
    elif all(status in {"PASS", "NOT_APPLICABLE"} for status in statuses):
        overall = "PASS"
    else:
        overall = "INCONCLUSIVE"
    compatible = {
        "schema_version": "1.0",
        "plan_id": plan["plan_id"],
        "run_id": plan["run_id"],
        "status": overall,
        "evidence_gate": gate,
        "oracles": oracle_results,
    }
    if resolution is not None:
        compatible["sequence_obligations"] = resolution
    return enrich_evaluation(compatible)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        events = read_trace(args.trace)
        result = evaluate(events, plan)
        if args.output.exists():
            raise ValueError(f"refusing to overwrite output: {args.output}")
        write_evaluation(args.output, result)
    except (OSError, ValueError, PlanError, RouteModelError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return {"PASS": 0, "VIOLATION": 1, "INCONCLUSIVE": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
