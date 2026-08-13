#!/usr/bin/env python3
"""Validate strict matched blocks and compute differential signals."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from itertools import combinations
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any

from scripts.analysis.corpus import CorpusError, file_digest, load_frozen_corpus


class MatchedDifferentialError(ValueError):
    """A matched-block input is structurally incomplete or output already exists."""


PROFILES = {
    "ROUTE_HANDOFF",
    "PROCESS_LOSS_FALLBACK",
    "SETPOINT_STALL_HEALTHY",
}
MECHANISMS = {
    "legacy_offboard",
    "dynamic_external_mode",
    "mode_executor",
}
CORE_MATCH_FIELDS = (
    "abstract_task",
    "setpoint_level",
    "fault_semantics",
    "successor_semantics",
    "fallback_semantics",
)
OPERATIONAL_MATCH_FIELDS = (
    "simulation_seed",
    "fault_seed",
    "schedule_seed",
    "cpu_set",
    "load_profile",
    "observer_config_digest",
    "environment_digest",
    "common_software_digest",
)
TIMING_TOLERANCE_NS = 20_000_000
NUMERIC_OBSERVATIONS = (
    "route_installation_latency_ns",
    "revocation_latency_ns",
    "maximum_command_age_ns",
    "successor_installation_latency_ns",
    "fallback_installation_latency_ns",
)
CATEGORICAL_OBSERVATIONS = (
    "route_installed",
    "route_revoked",
    "lineage_complete",
    "owner_matches_expected",
    "successor_installed",
    "fallback_installed",
    "physical_outcome",
)
COMPATIBLE_STATUSES = {"PASS", "VIOLATION", "INCONCLUSIVE"}
SEMANTIC_DISPOSITIONS = {
    "SPEC_VIOLATION",
    "SAFETY_CONTRACT_VIOLATION",
    "DIFFERENTIAL_DIVERGENCE",
    "PASS",
    "UNKNOWN",
    "NOT_APPLICABLE",
}


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def block_id_for(profile: str, declared_match: dict[str, Any]) -> str:
    """Derive the immutable block identity from every declared match field."""

    return _canonical_digest(
        {"schema_version": "1.0", "profile": profile, "declared_match": declared_match}
    )


def pair_id_for(block_id: str, mechanisms: list[str]) -> str:
    return _canonical_digest(
        {"block_id": block_id, "mechanisms": sorted(mechanisms)}
    )


def _require_fields(value: dict[str, Any], names: tuple[str, ...], context: str) -> None:
    missing = [name for name in names if name not in value]
    if missing:
        raise MatchedDifferentialError(
            f"{context} omits required fields: {', '.join(missing)}"
        )


def validate_block_shape(block: dict[str, Any]) -> None:
    """Fail closed on malformed records; semantic mismatches remain analyzable."""

    if not isinstance(block, dict) or block.get("schema_version") != "1.0":
        raise MatchedDifferentialError("matched block must use schema_version 1.0")
    _require_fields(block, ("block_id", "profile", "declared_match", "arms"), "block")
    if block["profile"] not in PROFILES:
        raise MatchedDifferentialError("unsupported matched comparison profile")
    declared = block["declared_match"]
    if not isinstance(declared, dict):
        raise MatchedDifferentialError("declared_match must be an object")
    _require_fields(
        declared,
        CORE_MATCH_FIELDS + OPERATIONAL_MATCH_FIELDS + ("planned_action_offset_ns",),
        "declared_match",
    )
    arms = block["arms"]
    if not isinstance(arms, list) or not arms:
        raise MatchedDifferentialError("arms must be a non-empty array")
    for index, arm in enumerate(arms):
        if not isinstance(arm, dict):
            raise MatchedDifferentialError(f"arm {index} must be an object")
        _require_fields(
            arm,
            (
                "arm_id",
                "mechanism",
                "attempt_id",
                "treatment_description",
                "realized_match",
                "evidence_gate",
                "correctness",
                "observations",
            ),
            f"arm {index}",
        )
        if arm["mechanism"] not in MECHANISMS:
            raise MatchedDifferentialError(f"arm {index} has unsupported mechanism")
        if arm["evidence_gate"] not in {"ADMISSIBLE", "INADMISSIBLE"}:
            raise MatchedDifferentialError(f"arm {index} has invalid evidence gate")
        treatment = arm["treatment_description"]
        if not isinstance(treatment, dict):
            raise MatchedDifferentialError(f"arm {index} treatment must be an object")
        _require_fields(treatment, ("fixture", "adapter", "code_path"), f"arm {index} treatment")
        realized = arm["realized_match"]
        if not isinstance(realized, dict):
            raise MatchedDifferentialError(f"arm {index} realized_match must be an object")
        _require_fields(
            realized,
            CORE_MATCH_FIELDS + OPERATIONAL_MATCH_FIELDS + ("actual_action_offset_ns",),
            f"arm {index} realized_match",
        )
        correctness = arm["correctness"]
        if (
            not isinstance(correctness, dict)
            or correctness.get("top_level") not in COMPATIBLE_STATUSES
            or not isinstance(correctness.get("semantic_vector"), list)
            or not correctness["semantic_vector"]
            or any(
                value not in SEMANTIC_DISPOSITIONS
                for value in correctness["semantic_vector"]
            )
        ):
            raise MatchedDifferentialError(f"arm {index} has invalid correctness vector")
        observations = arm["observations"]
        if not isinstance(observations, dict):
            raise MatchedDifferentialError(f"arm {index} observations must be an object")
        _require_fields(
            observations,
            NUMERIC_OBSERVATIONS
            + CATEGORICAL_OBSERVATIONS
            + (
                "observed_owner",
                "observation_completeness",
                "direct_observation_fields",
            ),
            f"arm {index} observations",
        )
        completeness = observations["observation_completeness"]
        if not isinstance(completeness, (int, float)) or not 0 <= completeness <= 1:
            raise MatchedDifferentialError(
                f"arm {index} observation_completeness must be in [0, 1]"
            )


def _reason(
    code: str,
    field: str,
    expected: Any,
    realized: dict[str, Any],
) -> dict[str, Any]:
    return {
        "code": code,
        "field": field,
        "expected": expected,
        "realized_by_arm": realized,
    }


def _match_reasons(block: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    declared = block["declared_match"]
    arms = block["arms"]
    fatal: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    expected_id = block_id_for(block["profile"], declared)
    if block["block_id"] != expected_id:
        fatal.append(
            _reason(
                "BLOCK_ID_MISMATCH",
                "block_id",
                expected_id,
                {"declared": block["block_id"]},
            )
        )
    mechanisms = [str(arm["mechanism"]) for arm in arms]
    if len(arms) < 2:
        fatal.append(_reason("INSUFFICIENT_ARMS", "arms", ">=2", {"count": len(arms)}))
    if len(set(mechanisms)) != len(mechanisms):
        fatal.append(
            _reason(
                "DUPLICATE_MECHANISM",
                "mechanism",
                "unique mechanisms",
                {str(index): mechanism for index, mechanism in enumerate(mechanisms)},
            )
        )

    profile_fault = {
        "PROCESS_LOSS_FALLBACK": "process_exit",
        "SETPOINT_STALL_HEALTHY": "setpoint_stall_health_maintained",
    }.get(block["profile"])
    if profile_fault is not None and declared["fault_semantics"] != profile_fault:
        fatal.append(
            _reason(
                "PROFILE_SEMANTICS_MISMATCH",
                "fault_semantics",
                profile_fault,
                {"declared": declared["fault_semantics"]},
            )
        )

    for field in CORE_MATCH_FIELDS:
        realized = {
            str(arm["arm_id"]): arm["realized_match"][field] for arm in arms
        }
        if any(value != declared[field] for value in realized.values()):
            fatal.append(
                _reason("SEMANTIC_FIELD_MISMATCH", field, declared[field], realized)
            )
    for field in OPERATIONAL_MATCH_FIELDS:
        realized = {
            str(arm["arm_id"]): arm["realized_match"][field] for arm in arms
        }
        if any(value != declared[field] for value in realized.values()):
            partial.append(
                _reason("STRICT_FIELD_MISMATCH", field, declared[field], realized)
            )

    offsets = {
        str(arm["arm_id"]): int(arm["realized_match"]["actual_action_offset_ns"])
        for arm in arms
    }
    planned = int(declared["planned_action_offset_ns"])
    if (
        any(abs(value - planned) > TIMING_TOLERANCE_NS for value in offsets.values())
        or max(offsets.values()) - min(offsets.values()) > TIMING_TOLERANCE_NS
    ):
        partial.append(
            _reason("ACTION_TIMING_MISMATCH", "actual_action_offset_ns", planned, offsets)
        )
    return fatal, partial


def _pair_result(block_id: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_obs = left["observations"]
    right_obs = right["observations"]
    latency_differences: dict[str, int | None] = {}
    divergent: list[str] = []
    for metric in NUMERIC_OBSERVATIONS:
        left_value = left_obs[metric]
        right_value = right_obs[metric]
        if left_value is None or right_value is None:
            latency_differences[metric] = None
            if left_value != right_value:
                divergent.append(f"missingness:{metric}")
        else:
            difference = int(left_value) - int(right_value)
            latency_differences[metric] = difference
            if difference != 0:
                divergent.append(metric)
    categorical_values: dict[str, dict[str, Any]] = {}
    for field in CATEGORICAL_OBSERVATIONS:
        values = {
            str(left["mechanism"]): left_obs[field],
            str(right["mechanism"]): right_obs[field],
        }
        categorical_values[field] = values
        if left_obs[field] != right_obs[field]:
            divergent.append(field)
    direct_fields = {
        str(left["mechanism"]): sorted(left_obs["direct_observation_fields"]),
        str(right["mechanism"]): sorted(right_obs["direct_observation_fields"]),
    }
    if list(direct_fields.values())[0] != list(direct_fields.values())[1]:
        divergent.append("direct_observation_fields")
    if left_obs["observation_completeness"] != right_obs["observation_completeness"]:
        divergent.append("observation_completeness")
    if left["correctness"] != right["correctness"]:
        divergent.append("correctness_verdict_vector")
    divergent = sorted(set(divergent))
    mechanisms = [str(left["mechanism"]), str(right["mechanism"])]
    signature = {
        "divergence_signature_id": _canonical_digest(
            {"mechanisms": sorted(mechanisms), "dimensions": divergent}
        ),
        "dimensions": divergent,
    }
    return {
        "pair_id": pair_id_for(block_id, mechanisms),
        "mechanisms": mechanisms,
        "paired_latency_differences_ns": latency_differences,
        "paired_verdict_vector": {
            str(left["mechanism"]): left["correctness"]["top_level"],
            str(right["mechanism"]): right["correctness"]["top_level"],
        },
        "paired_semantic_vectors": {
            str(left["mechanism"]): left["correctness"]["semantic_vector"],
            str(right["mechanism"]): right["correctness"]["semantic_vector"],
        },
        "observed_owner_vector": {
            str(left["mechanism"]): left_obs["observed_owner"],
            str(right["mechanism"]): right_obs["observed_owner"],
        },
        "categorical_observation_vectors": categorical_values,
        "direct_observation_field_vectors": direct_fields,
        "divergence_signature": signature,
        "semantic_disposition": "DIFFERENTIAL_DIVERGENCE" if divergent else "PASS",
        "correctness_verdicts_unchanged": True,
    }


def analyze_block(block: dict[str, Any]) -> dict[str, Any]:
    validate_block_shape(block)
    fatal, partial = _match_reasons(block)
    match_status = (
        "UNMATCHED" if fatal else "PARTIALLY_MATCHED" if partial else "FULLY_MATCHED"
    )
    exclusion: list[dict[str, Any]] = []
    inadmissible = [
        str(arm["arm_id"])
        for arm in block["arms"]
        if arm["evidence_gate"] != "ADMISSIBLE"
    ]
    if inadmissible:
        exclusion.append(
            {
                "code": "INADMISSIBLE_ARM",
                "arm_ids": inadmissible,
                "effect": "block retained descriptively but excluded from paired estimates",
            }
        )
    if match_status != "FULLY_MATCHED":
        exclusion.append(
            {
                "code": "MATCH_STATUS_NOT_FULL",
                "match_status": match_status,
                "effect": "block retained descriptively but excluded from paired estimates",
            }
        )
    eligible = match_status == "FULLY_MATCHED" and not exclusion
    pairs = (
        [_pair_result(block["block_id"], left, right) for left, right in combinations(block["arms"], 2)]
        if eligible
        else []
    )
    return {
        "schema_version": "1.0",
        "block_id": block["block_id"],
        "profile": block["profile"],
        "match_status": match_status,
        "mismatch_reasons": fatal + partial,
        "paired_estimate_eligible": eligible,
        "estimate_exclusion_reasons": exclusion,
        "arm_count": len(block["arms"]),
        "attempt_ids": [arm["attempt_id"] for arm in block["arms"]],
        "mechanism_treatments": {
            arm["mechanism"]: arm["treatment_description"] for arm in block["arms"]
        },
        "pairs": pairs,
        "correctness_is_independent": True,
    }


def _effect_summary(
    pair_key: tuple[str, str], metric: str, differences: list[int]
) -> dict[str, Any]:
    mean = statistics.mean(differences)
    standard_deviation = statistics.stdev(differences) if len(differences) >= 2 else None
    dz = (
        float(mean / standard_deviation)
        if standard_deviation not in (None, 0)
        else None
    )
    return {
        "mechanisms": list(pair_key),
        "metric": metric,
        "difference_orientation": f"{pair_key[0]} minus {pair_key[1]}",
        "complete_pair_count": len(differences),
        "mean_difference_ns": int(mean),
        "median_difference_ns": int(statistics.median(differences)),
        "minimum_difference_ns": min(differences),
        "maximum_difference_ns": max(differences),
        "standardized_effect_dz": dz,
    }


def analyze_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    results = [analyze_block(block) for block in blocks]
    grouped: dict[tuple[tuple[str, str], str], list[int]] = defaultdict(list)
    signatures: Counter[str] = Counter()
    for result in results:
        for pair in result["pairs"]:
            pair_key = tuple(pair["mechanisms"])
            signatures[pair["divergence_signature"]["divergence_signature_id"]] += 1
            for metric, value in pair["paired_latency_differences_ns"].items():
                if value is not None:
                    grouped[(pair_key, metric)].append(int(value))
    effects = [
        _effect_summary(pair_key, metric, values)
        for (pair_key, metric), values in sorted(grouped.items())
    ]
    return {
        "schema_version": "1.0",
        "analysis_kind": "matched_block_differential",
        "block_count": len(results),
        "match_status_counts": dict(Counter(item["match_status"] for item in results)),
        "eligible_block_count": sum(item["paired_estimate_eligible"] for item in results),
        "paired_effects": effects,
        "divergence_signature_counts": dict(sorted(signatures.items())),
        "interpretation": {
            "differential_defines_correctness": False,
            "unmatched_enters_paired_estimate": False,
            "partial_enters_paired_estimate": False,
            "inadmissible_enters_paired_estimate": False,
        },
        "block_results": results,
    }


def motivation_unpaired_descriptive(root: Path) -> list[dict[str, Any]]:
    """Record why the frozen corpus cannot be retroactively paired."""

    root = root.resolve()
    return [
        {
            "schema_version": "1.0",
            "study_id": record.study_id,
            "attempt_id": record.attempt_id,
            "cell_id": record.cell_id,
            "pairing_status": "UNMATCHED",
            "reason_code": "NO_PREREGISTERED_MATCHED_BLOCK",
            "reason": "seed and cell assignments were not registered as a common matched block",
            "descriptive_use_only": True,
            "input_digests": {
                "plan": record.plan_digest,
                "trace": record.trace_digest,
                "frozen_evaluation": record.frozen_evaluation_digest,
            },
        }
        for record in load_frozen_corpus(root)
    ]


def _read_blocks(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    blocks = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise MatchedDifferentialError(f"block line {line_number} is not an object")
        blocks.append(value)
    return blocks


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise MatchedDifferentialError(f"refusing to overwrite differential output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(
    root: Path,
    output_root: Path,
    blocks_path: Path | None = None,
    motivation_smoke: bool = False,
) -> dict[str, Any]:
    blocks = _read_blocks(blocks_path)
    summary = analyze_blocks(blocks)
    motivation = motivation_unpaired_descriptive(root) if motivation_smoke else []
    corpus = load_frozen_corpus(root) if motivation_smoke else []
    summary["motivation_unpaired_descriptive_count"] = len(motivation)
    _write_new(
        output_root / "block-results.jsonl",
        "".join(
            json.dumps(item, sort_keys=True) + "\n"
            for item in summary.pop("block_results")
        ),
    )
    _write_new(
        output_root / "motivation-unpaired.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in motivation),
    )
    _write_new(
        output_root / "input-manifest.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "matched_block_input": (
                    {
                        "path": str(blocks_path.relative_to(root)),
                        "sha256": file_digest(blocks_path),
                    }
                    if blocks_path is not None
                    else None
                ),
                "frozen_motivation_inputs": [
                    record.manifest_entry(root) for record in corpus
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_new(
        output_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--blocks", type=Path)
    parser.add_argument("--motivation-smoke", action="store_true")
    args = parser.parse_args()
    try:
        summary = run(
            args.root.resolve(),
            args.output_root.resolve(),
            args.blocks.resolve() if args.blocks else None,
            args.motivation_smoke,
        )
    except (
        CorpusError,
        MatchedDifferentialError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
