#!/usr/bin/env python3
"""Build blank V0-P compact-evidence templates and validate completed evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.fuzzer_v0.family_a.common import (
    ROOT,
    load_manifest,
    load_scenario_map,
    sha256,
)


SCHEMA_PATH = (
    ROOT / "data/schemas/family_a_fuzzer_v0_compact_evidence.schema.json"
)
ORACLE_OUTCOMES = {"PASS", "EXPOSURE", "VIOLATION", "UNKNOWN", "NOT_APPLICABLE"}
ATTEMPT_CLASSIFICATIONS = {
    "ACCEPTED",
    "OBSERVABILITY_REJECTED",
    "MEASUREMENT_INSUFFICIENT",
    "ENVIRONMENT_FAILURE",
    "CAMPAIGN_CONFIGURATION_FAILURE",
    "FORMAL_SAFETY_STOP",
    "NOT_APPLICABLE",
}
ORACLE_KEY = {
    "ROUTE": "route",
    "FRESHNESS": "freshness",
    "SUCCESSOR": "successor",
    "LINEARIZATION": "linearization",
}


class EvidenceError(ValueError):
    """Compact evidence is incomplete or changes frozen outcome semantics."""


def _component_identities(paths: list[str]) -> list[dict[str, str]]:
    manifest = load_manifest()
    by_path = {item["path"]: item for item in manifest["components"]}
    return [
        {
            "path": path,
            "version": str(by_path[path]["version"]),
            "sha256": str(by_path[path]["sha256"]),
        }
        for path in paths
    ]


def template(slot_id: str) -> dict[str, Any]:
    rows = {row["slot_id"]: row for row in load_scenario_map()}
    if slot_id not in rows:
        raise EvidenceError(f"slot is not in the qualification map: {slot_id}")
    row = rows[slot_id]
    manifest = load_manifest()
    binding = next(
        item for item in manifest["orchestration_bindings"] if item["slot_id"] == slot_id
    )
    expected = set(row["expected_oracles"].split("|"))
    oracle_paths = list(binding["oracle_bundle"])
    return {
        "schema_version": "1.0",
        "template_only": True,
        "attempt_identity": {
            "attempt_id": row["attempt_id"],
            "phase": "V0_P_QUALIFICATION",
            "formal_attempt_registered": False,
        },
        "repository_identity": {
            "commit": None,
            "worktree_clean": None,
        },
        "dependency_identity": {
            "lock_path": "config/dependencies.lock.yaml",
            "lock_sha256": sha256(ROOT / "config/dependencies.lock.yaml"),
        },
        "slot_id": slot_id,
        "seed_id": row["seed_id"],
        "scenario_identity": {
            "scenario_family": row["scenario_family"],
            "simulation_seed": int(row["simulation_seed"]),
            "scenario_entry": binding["scenario_entry"],
        },
        "adapter_identity": _component_identities(list(binding["adapter_entries"])),
        "collector_identities": _component_identities(
            list(binding["collector_bundle"])
        ),
        "oracle_identities": _component_identities(oracle_paths),
        "raw_artifact_manifest_hashes": {},
        "critical_window_status": None,
        "clock_status": None,
        "route_result": None if "ROUTE" in expected else "NOT_APPLICABLE",
        "freshness_result": (
            None if "FRESHNESS" in expected else "NOT_APPLICABLE"
        ),
        "successor_result": (
            None if "SUCCESSOR" in expected else "NOT_APPLICABLE"
        ),
        "linearization_result": (
            None if "LINEARIZATION" in expected else "NOT_APPLICABLE"
        ),
        "evidence_gate_classification": None,
        "safety_result": None,
        "cleanup_result": None,
        "process_port_audit": None,
        "final_attempt_classification": None,
    }


def _validate_identity_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or not value:
        raise EvidenceError(f"{field} must contain one or more identities")
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "version", "sha256"}:
            raise EvidenceError(f"{field} contains an invalid identity")
        path = ROOT / str(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise EvidenceError(f"{field} identity mismatch: {item['path']}")


def validate_evidence(value: dict[str, Any], *, require_complete: bool) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(value)
    rows = {row["slot_id"]: row for row in load_scenario_map()}
    row = rows.get(str(value["slot_id"]))
    if row is None or value["seed_id"] != row["seed_id"]:
        raise EvidenceError("slot and seed do not match the qualification map")
    if value["attempt_identity"]["attempt_id"] != row["attempt_id"]:
        raise EvidenceError("attempt and slot do not match the fixed schedule")
    _validate_identity_list(value["adapter_identity"], "adapter_identity")
    _validate_identity_list(value["collector_identities"], "collector_identities")
    _validate_identity_list(value["oracle_identities"], "oracle_identities")
    if not require_complete:
        if value["template_only"] is not True:
            raise EvidenceError("an incomplete record must be marked template_only")
        return

    if value["template_only"] is not False:
        raise EvidenceError("completed evidence cannot be marked template_only")
    required_non_null = (
        ("repository_identity.commit", value["repository_identity"]["commit"]),
        (
            "repository_identity.worktree_clean",
            value["repository_identity"]["worktree_clean"],
        ),
        ("critical_window_status", value["critical_window_status"]),
        ("clock_status", value["clock_status"]),
        ("evidence_gate_classification", value["evidence_gate_classification"]),
        ("safety_result", value["safety_result"]),
        ("cleanup_result", value["cleanup_result"]),
        ("process_port_audit", value["process_port_audit"]),
        ("final_attempt_classification", value["final_attempt_classification"]),
    )
    missing = [name for name, item in required_non_null if item is None]
    if missing:
        raise EvidenceError("missing completed evidence: " + ", ".join(missing))
    if not value["raw_artifact_manifest_hashes"]:
        raise EvidenceError("raw artifact manifest hashes are required")

    expected = set(row["expected_oracles"].split("|"))
    for oracle, key in ORACLE_KEY.items():
        result = value[f"{key}_result"]
        if result not in ORACLE_OUTCOMES:
            raise EvidenceError(f"{key} Oracle result is invalid or missing")
        if oracle in expected and result == "NOT_APPLICABLE":
            raise EvidenceError(f"applicable {key} Oracle cannot be NOT_APPLICABLE")
        if oracle not in expected and result != "NOT_APPLICABLE":
            raise EvidenceError(f"non-applicable {key} Oracle must remain NOT_APPLICABLE")

    classification = value["final_attempt_classification"]
    if classification not in ATTEMPT_CLASSIFICATIONS:
        raise EvidenceError("final attempt classification is invalid")
    if classification == "ACCEPTED":
        applicable_results = [
            value[f"{ORACLE_KEY[name]}_result"] for name in expected
        ]
        if "UNKNOWN" in applicable_results:
            raise EvidenceError("UNKNOWN Oracle result cannot produce ACCEPTED")
        if value["clock_status"] not in {"VALID", "NOT_REQUIRED"}:
            raise EvidenceError("missing or invalid clock cannot produce ACCEPTED")
        if value["critical_window_status"] != "COMPLETE":
            raise EvidenceError("incomplete critical window cannot produce ACCEPTED")
        if value["evidence_gate_classification"] != "ACCEPTED":
            raise EvidenceError("Evidence Gate must classify an ACCEPTED attempt")
        if value["safety_result"] != "PASS":
            raise EvidenceError("non-PASS safety result cannot produce ACCEPTED")
        if value["cleanup_result"] != "CLEAN":
            raise EvidenceError("non-CLEAN cleanup result cannot produce ACCEPTED")
        if value["process_port_audit"] != "CLEAN":
            raise EvidenceError("non-CLEAN process/port audit cannot produce ACCEPTED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    make = subparsers.add_parser("template")
    make.add_argument("--slot-id", required=True)
    make.add_argument("--output", type=Path, required=True)
    check = subparsers.add_parser("validate")
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--allow-template", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "template":
            value = template(args.slot_id)
            validate_evidence(value, require_complete=False)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "status": "TEMPLATE_VALID",
                        "runtime_result_generated": False,
                        "output": str(args.output),
                    },
                    sort_keys=True,
                )
            )
        else:
            value = json.loads(args.input.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise EvidenceError("compact evidence root must be an object")
            validate_evidence(value, require_complete=not args.allow_template)
            print(json.dumps({"status": "VALID"}, sort_keys=True))
    except (EvidenceError, jsonschema.ValidationError, KeyError, ValueError) as exc:
        print(json.dumps({"status": "INVALID", "error": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
