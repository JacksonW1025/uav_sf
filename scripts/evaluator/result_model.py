#!/usr/bin/env python3
"""Backward-compatible semantic model for Family A evaluation results."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


COMPATIBLE_STATUSES = {"PASS", "VIOLATION", "INCONCLUSIVE"}
SEMANTIC_DISPOSITIONS = {
    "SPEC_VIOLATION",
    "SAFETY_CONTRACT_VIOLATION",
    "DIFFERENTIAL_DIVERGENCE",
    "PASS",
    "UNKNOWN",
    "NOT_APPLICABLE",
}
FINDING_CLASSIFICATIONS = {
    "PUBLIC_SPEC_GROUNDED",
    "RESEARCH_SAFETY_CONTRACT",
    "SAFETY_RELEVANT_EXPOSURE",
    "SOFTWARE_OR_DIAGNOSTIC_ANOMALY",
    "THRESHOLD_SENSITIVE_ANOMALY",
    "POSSIBLE_EXPERIMENT_OR_ORACLE_ARTIFACT",
}


class EvaluationResultError(ValueError):
    """Evaluation result violates the compatibility contract."""


_THRESHOLD_FIELDS = {
    ("route_conformance", "revocation"): "revocation_deadline_ns",
    ("route_conformance", "installation"): "installation_deadline_ns",
    ("route_conformance", "continuity"): "maximum_effect_gap_ns",
    ("freshness_lineage", "freshness"): "maximum_command_age_ns",
    ("successor_progression", "expected_successor"): "successor_deadline_ns",
    ("successor_progression", "safe_fallback"): "fallback_deadline_ns",
    ("successor_progression", "adjacent_timing"): "successor_deadline_ns",
    ("successor_progression", "adjacent_order"): "successor_deadline_ns",
    ("successor_progression", "adjacent_successor"): "successor_deadline_ns",
}


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _classifications(oracle: str, name: str, disposition: str) -> list[str]:
    values: set[str] = set()
    if disposition == "SPEC_VIOLATION":
        values.add("PUBLIC_SPEC_GROUNDED")
    if disposition == "SAFETY_CONTRACT_VIOLATION":
        values.update({"RESEARCH_SAFETY_CONTRACT", "SAFETY_RELEVANT_EXPOSURE"})
    if (oracle, name) in _THRESHOLD_FIELDS:
        values.add("THRESHOLD_SENSITIVE_ANOMALY")
    if oracle == "registration_contract":
        values.add("SOFTWARE_OR_DIAGNOSTIC_ANOMALY")
    return sorted(values)


def _contract_provenance(oracle: str, name: str) -> dict[str, Any]:
    threshold = _THRESHOLD_FIELDS.get((oracle, name))
    return {
        "kind": "RESEARCH_SAFETY_CONTRACT",
        "source": "preregistered experiment plan",
        "public_spec_reference": None,
        "threshold_field": threshold,
    }


def _finding(
    oracle: str,
    name: str,
    clause: dict[str, Any],
    disposition: str,
) -> dict[str, Any]:
    material = {
        "oracle": oracle,
        "clause": name,
        "status": clause.get("status"),
        "reasons": clause.get("reasons", []),
        "evidence": clause.get("evidence", {}),
        "semantic_disposition": disposition,
    }
    return {
        "finding_id": _canonical_digest(material),
        "oracle": oracle,
        "clause": name,
        "clause_status": clause["status"],
        "semantic_disposition": disposition,
        "contract_provenance": _contract_provenance(oracle, name),
        "classifications": _classifications(oracle, name, disposition),
        "reasons": list(clause.get("reasons", [])),
        "evidence": copy.deepcopy(clause.get("evidence", {})),
    }


def enrich_evaluation(result: dict[str, Any]) -> dict[str, Any]:
    """Add v1.1 semantics without changing the v1 top-level verdict."""

    validate_evaluation(result, allow_v1=True)
    enriched = copy.deepcopy(result)
    enriched["schema_version"] = "1.1"
    gate = enriched["evidence_gate"]
    clauses = [
        (str(oracle.get("oracle", "")), str(name), value)
        for oracle in enriched["oracles"]
        for name, value in oracle.get("clauses", {}).items()
        if isinstance(value, dict)
    ]
    findings: list[dict[str, Any]] = []
    dispositions: list[str] = []
    if gate["status"] == "ADMISSIBLE":
        for oracle, name, value in clauses:
            status = value.get("status")
            if status == "VIOLATION":
                disposition = str(
                    value.get("semantic_disposition", "SAFETY_CONTRACT_VIOLATION")
                )
                if disposition not in {
                    "SPEC_VIOLATION",
                    "SAFETY_CONTRACT_VIOLATION",
                    "DIFFERENTIAL_DIVERGENCE",
                }:
                    raise EvaluationResultError(
                        f"violation clause has invalid semantic disposition: {disposition}"
                    )
                findings.append(_finding(oracle, name, value, disposition))
                dispositions.append(disposition)
            elif status == "UNKNOWN":
                dispositions.append("UNKNOWN")
        if enriched["status"] == "PASS":
            dispositions = ["PASS"]
        elif enriched["status"] == "INCONCLUSIVE":
            dispositions.append("UNKNOWN")
    else:
        dispositions = ["UNKNOWN"]

    order = {
        "SPEC_VIOLATION": 0,
        "SAFETY_CONTRACT_VIOLATION": 1,
        "DIFFERENTIAL_DIVERGENCE": 2,
        "UNKNOWN": 3,
        "PASS": 4,
        "NOT_APPLICABLE": 5,
    }
    all_dispositions = sorted(set(dispositions), key=order.__getitem__)
    if not all_dispositions:
        all_dispositions = ["UNKNOWN"]
    enriched["semantic_disposition"] = {
        "primary": all_dispositions[0],
        "all": all_dispositions,
    }
    enriched["findings"] = findings
    enriched["evidence"] = {
        "admissibility": gate["status"],
        "oracle_count": len(enriched["oracles"]),
        "clause_count": len(clauses),
        "gate_reason_count": len(gate.get("reasons", [])),
    }
    validate_evaluation(enriched)
    return enriched


def validate_evaluation(result: dict[str, Any], *, allow_v1: bool = True) -> None:
    if not isinstance(result, dict):
        raise EvaluationResultError("evaluation root must be an object")
    version = result.get("schema_version")
    if version not in ({"1.0", "1.1"} if allow_v1 else {"1.1"}):
        raise EvaluationResultError("unsupported evaluation schema_version")
    for field in ("plan_id", "run_id"):
        if not isinstance(result.get(field), str) or not result[field]:
            raise EvaluationResultError(f"{field} must be a non-empty string")
    if result.get("status") not in COMPATIBLE_STATUSES:
        raise EvaluationResultError("invalid compatible top-level status")
    gate = result.get("evidence_gate")
    if not isinstance(gate, dict) or gate.get("status") not in {
        "ADMISSIBLE",
        "INADMISSIBLE",
    }:
        raise EvaluationResultError("invalid evidence gate")
    if gate["status"] == "INADMISSIBLE" and result["status"] != "INCONCLUSIVE":
        raise EvaluationResultError("inadmissible evidence must remain INCONCLUSIVE")
    if not isinstance(result.get("oracles"), list):
        raise EvaluationResultError("oracles must be an array")
    for oracle in result["oracles"]:
        if not isinstance(oracle, dict) or not isinstance(oracle.get("clauses"), dict):
            raise EvaluationResultError("oracle clauses must be an object")
        for value in oracle["clauses"].values():
            if not isinstance(value, dict) or value.get("status") not in {
                "PASS",
                "VIOLATION",
                "UNKNOWN",
                "NOT_APPLICABLE",
            }:
                raise EvaluationResultError("invalid clause status")
    if version == "1.0":
        return
    semantic = result.get("semantic_disposition")
    if not isinstance(semantic, dict):
        raise EvaluationResultError("v1.1 result omits semantic_disposition")
    values = semantic.get("all")
    if (
        semantic.get("primary") not in SEMANTIC_DISPOSITIONS
        or not isinstance(values, list)
        or not values
        or semantic["primary"] not in values
        or any(value not in SEMANTIC_DISPOSITIONS for value in values)
    ):
        raise EvaluationResultError("invalid semantic disposition")
    findings = result.get("findings")
    if not isinstance(findings, list):
        raise EvaluationResultError("v1.1 result omits findings")
    for finding in findings:
        if not isinstance(finding, dict):
            raise EvaluationResultError("finding must be an object")
        if finding.get("semantic_disposition") not in SEMANTIC_DISPOSITIONS:
            raise EvaluationResultError("finding has invalid semantic disposition")
        categories = finding.get("classifications")
        if not isinstance(categories, list) or any(
            category not in FINDING_CLASSIFICATIONS for category in categories
        ):
            raise EvaluationResultError("finding has invalid classifications")
    if not isinstance(result.get("evidence"), dict):
        raise EvaluationResultError("v1.1 result omits evidence summary")


def load_evaluation(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_evaluation(value)
    return value


def write_evaluation(path: Path, result: dict[str, Any]) -> None:
    validate_evaluation(result)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evaluation: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
