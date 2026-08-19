#!/usr/bin/env python3
"""Qualify two mechanisms and three strategies without opening a formal ledger."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from scripts.corpus.core_actions import live_profile
from scripts.runtime.live_strategy_backend import CORPUS_SCHEMA, validate_live_decision
from scripts.runtime.run_qualification_batch import (
    QualificationBatchError,
    _active_containers,
    _namespace,
    _parallel,
)


STRATEGIES = ("official_sequence", "bounded_random_timing", "state_aware")
MECHANISMS = ("legacy_offboard", "dynamic_external_mode")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationBatchError(f"JSON root is not an object: {path}")
    return value


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise QualificationBatchError(f"JSONL record is not an object: {path}")
            values.append(value)
    return values


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _selected_unit(decision: dict[str, Any]) -> str:
    """The coverage unit a decision claims.

    A corpus decision covers an (action, timing) unit; the earlier
    single-action decision covers a timing boundary only.
    """

    if decision.get("schema_version") == CORPUS_SCHEMA:
        return str(decision["selected_unit"])
    return str(decision["selected_boundary"])


def _covered_units(decision: dict[str, Any]) -> list[str]:
    if decision.get("schema_version") == CORPUS_SCHEMA:
        return list(decision["covered_units_before_decision"])
    return list(decision["covered_boundaries_before_decision"])


def _cell_key(cell: dict[str, Any]) -> tuple[str, str]:
    return str(cell.get("mechanism")), str(cell.get("strategy"))


def _validate_spec(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    if spec.get("schema_version") != "1.0" or spec.get("qualification_only") is not True:
        raise QualificationBatchError("strategy qualification spec is not explicitly non-formal")
    if int(spec.get("rounds", 0)) != 3 or int(spec.get("concurrency_per_round", 0)) != 3:
        raise QualificationBatchError("qualification requires three rounds of three strategies")
    cells = {_cell_key(cell): cell for cell in spec.get("cells", [])}
    expected = {(mechanism, strategy) for mechanism in MECHANISMS for strategy in STRATEGIES}
    if set(cells) != expected or len(spec.get("cells", [])) != len(expected):
        raise QualificationBatchError("qualification must cross two mechanisms and three strategies")
    if len(set(str(cell.get("attempt_id_prefix", "")) for cell in cells.values())) != 6:
        raise QualificationBatchError("qualification attempt prefixes must be unique")
    if len(spec.get("resources", {}).get("cpu_sets", [])) != 4:
        raise QualificationBatchError("qualification requires four frozen CPU sets")
    if Path(spec["formal_ledger_path"]).exists():
        raise QualificationBatchError("formal attempt ledger already exists; qualification must not open it")
    corpus = spec.get("corpus", [])
    if corpus:
        if spec.get("live_strategy_backend") is not None:
            raise QualificationBatchError(
                "a corpus qualification selects its own action and must not pin one backend"
            )
        if not isinstance(corpus, list) or not all(isinstance(item, str) for item in corpus):
            raise QualificationBatchError("qualification corpus must be a list of action names")
        official = spec.get("official_action")
        if official not in corpus:
            raise QualificationBatchError("the official action must belong to the corpus")
        for action in corpus:
            live_profile(action)
        bounds = spec.get("attempt", {}).get("timing_bounds_ns", {})
        missing = sorted(set(corpus) - set(bounds))
        if missing:
            raise QualificationBatchError(
                "the corpus needs timing bounds for: " + ", ".join(missing)
            )
    elif spec.get("live_strategy_backend") is None:
        raise QualificationBatchError("qualification needs a corpus or a live strategy backend")
    return cells


def _observed_coverage(run_root: Path, study_id: str, prefix: str) -> list[str]:
    values = []
    decision_root = run_root / study_id / "strategy-decisions"
    for decision_path in sorted(decision_root.glob(prefix + "-*.json")):
        attempt_id = decision_path.stem
        lifecycle = run_root / study_id / attempt_id / "raw" / "strategy.lifecycle.jsonl"
        if any(record.get("kind") == "action_requested" for record in _records(lifecycle)):
            decision = _read_object(decision_path)
            validate_live_decision(decision)
            # A corpus decision covers an (action, timing) unit; the earlier
            # single-action decision covers a timing boundary only.
            values.append(_selected_unit(decision))
    return sorted(set(values))


def _fallback_status(evaluation_path: Path) -> str | None:
    # An observability-rejected attempt closes without an evaluation.  That is a
    # failed qualification attempt, not a reason to abandon the whole batch.
    if not evaluation_path.is_file():
        return None
    evaluation = _read_object(evaluation_path)
    for oracle in evaluation.get("oracles", []):
        if oracle.get("oracle") == "successor_progression":
            return oracle.get("clauses", {}).get("safe_fallback", {}).get("status")
    return None


def _attempt_summary(
    *, run_root: Path, study_id: str, attempt_id: str, result: dict[str, Any]
) -> dict[str, Any]:
    attempt_root = run_root / study_id / attempt_id
    decision_path = run_root / study_id / "strategy-decisions" / f"{attempt_id}.json"
    decision = _read_object(decision_path)
    validate_live_decision(decision)
    lifecycle_path = attempt_root / "raw" / "strategy.lifecycle.jsonl"
    lifecycle = _records(lifecycle_path)
    action_records = [value for value in lifecycle if value.get("kind") == "action_requested"]
    complete_lifecycle = [value.get("kind") for value in lifecycle] == [
        "strategy_decision",
        "action_scheduled",
        "action_requested",
    ]
    action_valid = (
        len(action_records) == 1
        and action_records[0].get("action") == decision["action"]
        and action_records[0].get("selected_boundary") == decision["selected_boundary"]
    )
    physical = result.get("physical_execution", {})
    fallback = _fallback_status(attempt_root / "derived" / "evaluation.json")
    if decision.get("schema_version") == CORPUS_SCHEMA:
        # A stall action owes no fallback, so requiring one would fail a
        # correct flight.  Each action is held to its own obligation.
        expects_fallback = live_profile(str(decision["action"])).fallback_expected
    else:
        expects_fallback = True
    fallback_ok = (
        fallback == "PASS"
        if expects_fallback
        else fallback is not None and fallback != "VIOLATION"
    )
    passed = all(
        (
            result.get("outcome") == "ACCEPTED",
            result.get("evidence_gate_status") == "ADMISSIBLE",
            result.get("ulog", {}).get("status") == "PASS",
            physical.get("status") == "PASS",
            fallback_ok,
            complete_lifecycle,
            action_valid,
        )
    )
    return {
        "attempt_id": attempt_id,
        "outcome": result.get("outcome"),
        "evidence_gate_status": result.get("evidence_gate_status"),
        "physical_execution_status": physical.get("status"),
        "safe_fallback_status": fallback,
        "safe_fallback_required": expects_fallback,
        "evaluated": (attempt_root / "derived" / "evaluation.json").is_file(),
        "selected_action": decision["action"],
        "strategy_lifecycle_complete": complete_lifecycle,
        "action_contract_valid": action_valid,
        "selected_boundary": decision["selected_boundary"],
        "selected_unit": _selected_unit(decision),
        "planned_offset_ns": decision["planned_offset_ns"],
        "covered_units_before_decision": _covered_units(decision),
        "decision_digest": _digest(decision_path),
        "passed": passed,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    spec = _read_object(args.spec)
    cells = _validate_spec(spec)
    if not Path(spec["attestation"]).is_file():
        raise QualificationBatchError("qualification attestation is missing")
    run_root = args.run_root
    study_id = str(spec["study_id"])
    if (run_root / study_id).exists():
        raise QualificationBatchError("qualification run root already exists")
    study_root = run_root / study_id
    study_root.mkdir(parents=True)
    shutil.copyfile(Path(spec["attestation"]), study_root / "environment.json")
    started_at = _now()
    process_results: dict[str, dict[str, Any]] = {}
    rounds = []
    for mechanism_index, mechanism in enumerate(MECHANISMS):
        for ordinal in range(1, 4):
            live_arguments = []
            for strategy_index, strategy in enumerate(STRATEGIES):
                cell = cells[(mechanism, strategy)]
                prefix = str(cell["attempt_id_prefix"])
                attempt_id = f"{prefix}-{ordinal:03d}"
                attempt = {
                    **spec["attempt"],
                    **cell,
                    "run_id": attempt_id,
                    "slot": (strategy_index + ordinal + mechanism_index) % 4,
                    "simulation_seed": int(cell["simulation_seed_base"]) + ordinal,
                    "covered_boundary": _observed_coverage(run_root, study_id, prefix),
                }
                if strategy != "official_sequence":
                    attempt["strategy_seed"] = int(cell["strategy_seed_base"]) + ordinal
                cpu_set = str(spec["resources"]["cpu_sets"][attempt["slot"]])
                live_arguments.append(
                    _namespace(
                        spec=spec,
                        attempt=attempt,
                        run_root=run_root,
                        cpu_set=cpu_set,
                        phase="live",
                    )
                )
            live_results, live_errors = _parallel(live_arguments, concurrency=3)
            active = _active_containers(study_id)
            if live_errors or active or len(live_results) != 3:
                raise QualificationBatchError(
                    "qualification live barrier failed: "
                    + json.dumps({"errors": live_errors, "active_containers": active}, sort_keys=True)
                )
            process_arguments = []
            for value in live_arguments:
                value.phase = "process"
                process_arguments.append(value)
            current_results, process_errors = _parallel(process_arguments, concurrency=3)
            if process_errors or len(current_results) != 3:
                raise QualificationBatchError(
                    "qualification processing barrier failed: " + json.dumps(process_errors, sort_keys=True)
                )
            process_results.update(current_results)
            rounds.append(
                {
                    "mechanism": mechanism,
                    "ordinal": ordinal,
                    "attempt_ids": sorted(current_results),
                    "barrier_passed": True,
                }
            )
    attempts = {
        attempt_id: _attempt_summary(
            run_root=run_root,
            study_id=study_id,
            attempt_id=attempt_id,
            result=result,
        )
        for attempt_id, result in sorted(process_results.items())
    }
    units = []
    feedback_checks = []
    for mechanism in MECHANISMS:
        for strategy in STRATEGIES:
            cell = cells[(mechanism, strategy)]
            prefix = str(cell["attempt_id_prefix"])
            unit_attempts = [attempts[f"{prefix}-{ordinal:03d}"] for ordinal in range(1, 4)]
            units.append(
                {
                    "mechanism": mechanism,
                    "strategy": strategy,
                    "attempt_count": len(unit_attempts),
                    "passed_count": sum(value["passed"] for value in unit_attempts),
                    "selected_boundaries": [value["selected_boundary"] for value in unit_attempts],
                    "selected_actions": [value["selected_action"] for value in unit_attempts],
                    "selected_units": [value["selected_unit"] for value in unit_attempts],
                    "status": "PASS" if all(value["passed"] for value in unit_attempts) else "FAIL",
                }
            )
            if strategy == "state_aware":
                feedback_ok = all(
                    set(unit_attempts[index]["covered_units_before_decision"])
                    == {value["selected_unit"] for value in unit_attempts[:index]}
                    and unit_attempts[index]["selected_unit"]
                    not in unit_attempts[index]["covered_units_before_decision"]
                    for index in range(1, 3)
                )
                feedback_checks.append(
                    {
                        "mechanism": mechanism,
                        "subsequent_decisions_used_live_feedback": feedback_ok,
                    }
                )
    passed = (
        len(attempts) == 18
        and all(value["passed"] for value in attempts.values())
        and len(units) == 6
        and all(value["status"] == "PASS" for value in units)
        and len(feedback_checks) == 2
        and all(value["subsequent_decisions_used_live_feedback"] for value in feedback_checks)
        and not Path(spec["formal_ledger_path"]).exists()
    )
    result = {
        "schema_version": "1.0",
        "qualification_only": True,
        "study_id": study_id,
        "started_at": started_at,
        "completed_at": _now(),
        "spec_digest": _digest(args.spec),
        "live_strategy_backend": spec.get("live_strategy_backend"),
        "corpus": list(spec.get("corpus", [])),
        "official_action": spec.get("official_action"),
        "rounds": rounds,
        "attempts": attempts,
        "units": units,
        "state_aware_feedback_checks": feedback_checks,
        "formal_campaign_started": Path(spec["formal_ledger_path"]).exists(),
        "status": "PASS" if passed else "FAIL",
    }
    if args.output.exists():
        raise QualificationBatchError("qualification result already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise QualificationBatchError("the six-unit qualification gate did not pass")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, default=Path("runs"))
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, QualificationBatchError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "study_id": result["study_id"],
                "attempt_count": len(result["attempts"]),
                "unit_count": len(result["units"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
