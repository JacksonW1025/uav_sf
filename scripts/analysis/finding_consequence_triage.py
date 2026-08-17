#!/usr/bin/env python3
"""Triage concentrated findings, physical exposures, and Dynamic timeouts."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
from typing import Any

from scripts.analysis.corpus import CorpusError, file_digest, load_frozen_corpus
from scripts.evaluator.plan import load_plan
from scripts.evaluator.result_model import load_evaluation
from scripts.model.runtime_route import read_trace
from scripts.oracles.common import complete_installation
from scripts.oracles.transition_scope import (
    matching_transition_requests,
    transition_window_end_ns,
)


class FindingTriageError(RuntimeError):
    """The frozen triage inputs are missing, inconsistent, or would be overwritten."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise FindingTriageError(f"non-object JSON at {path}:{line_number}")
        values.append(value)
    return values


def _distribution(values: list[int | float]) -> dict[str, int | float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "p90_nearest_rank": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum": ordered[-1],
    }


def _installation_status(evaluation: dict[str, Any]) -> str:
    for oracle in evaluation["oracles"]:
        if oracle["oracle"] == "route_conformance":
            return str(oracle["clauses"]["installation"]["status"])
    raise FindingTriageError("route_conformance installation clause is absent")


def _physical_statuses(root: Path) -> dict[tuple[str, str], str]:
    path = root / "experiments/posthoc_physical_execution_validity_v1/per-trace.jsonl"
    return {
        (item["study_id"], item["attempt_id"]): item["physical_execution_status"]
        for item in _read_jsonl(path)
    }


def installation_triage(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    physical_status = _physical_statuses(root)
    results = []
    manifest_entries = []
    for record in load_frozen_corpus(root):
        evaluation = load_evaluation(record.frozen_evaluation_path)
        if _installation_status(evaluation) != "VIOLATION":
            continue
        plan = load_plan(record.plan_path)
        events = read_trace(record.trace_path)
        requests = matching_transition_requests(events, plan)
        if len(requests) != 1:
            raise FindingTriageError(
                f"{record.attempt_id} installation triage expected one request"
            )
        request = requests[0]
        request_ns = int(request["timestamp_ns"])
        scope_end_ns = transition_window_end_ns(events, plan, request)
        installation = complete_installation(
            events,
            route=plan["transition"]["target_route"],
            anchor_ns=request_ns,
            deadline_ns=scope_end_ns,
        )
        if not installation.get("complete"):
            raise FindingTriageError(
                f"{record.attempt_id} never produces a late complete installation"
            )
        route_observations_path = (
            root
            / "runs"
            / record.study_id
            / record.attempt_id
            / "derived"
            / "route-observations.json"
        )
        processing_path = (
            root
            / "runs"
            / record.study_id
            / record.attempt_id
            / "processing_result.json"
        )
        route_observations = json.loads(route_observations_path.read_text(encoding="utf-8"))
        processing = json.loads(processing_path.read_text(encoding="utf-8"))
        positive_periods = [
            int(item["expected_period_us"])
            for item in route_observations
            if isinstance(item.get("expected_period_us"), int)
            and int(item["expected_period_us"]) > 0
        ]
        period_counts = Counter(positive_periods)
        dominant_period_us = period_counts.most_common(1)[0][0]
        profile_counts = Counter(int(item["profile"]) for item in route_observations)
        clock_uncertainty_ns = int(processing["clock_bridge"]["uncertainty_ns"])
        completed_at_ns = int(installation["completed_at_ns"])
        latency_ns = completed_at_ns - request_ns
        deadline_ns = int(plan["thresholds"]["installation_deadline_ns"])
        conservative_lower_ns = max(
            0,
            latency_ns - dominant_period_us * 1000 - clock_uncertainty_ns,
        )
        stage_offsets = {
            kind: int(event["timestamp_ns"]) - request_ns
            for kind, event in installation["events"].items()
        }
        result = {
            "schema_version": "1.0",
            "study_id": record.study_id,
            "attempt_id": record.attempt_id,
            "cell_id": record.cell_id,
            "physical_execution_status": physical_status[
                (record.study_id, record.attempt_id)
            ],
            "target_route": plan["transition"]["target_route"],
            "request_sequence": int(request["sequence"]),
            "installation_deadline_ns": deadline_ns,
            "observed_complete_installation_latency_ns": latency_ns,
            "stage_offsets_from_request_ns": stage_offsets,
            "observer": {
                "profile_counts": {str(key): value for key, value in profile_counts.items()},
                "positive_expected_period_us_counts": {
                    str(key): value for key, value in period_counts.items()
                },
                "dominant_expected_period_us": dominant_period_us,
                "clock_uncertainty_ns": clock_uncertainty_ns,
            },
            "conservative_latency_interval_ns": {
                "lower_after_one_period_and_clock_uncertainty": conservative_lower_ns,
                "upper_observed": latency_ns,
            },
            "definitely_exceeds_deadline_under_interval": (
                conservative_lower_ns > deadline_ns
            ),
            "classification": (
                "LATE_INSTALLATION_ROBUST_TO_ONE_PERIOD_AND_CLOCK_BOUND"
                if conservative_lower_ns > deadline_ns
                else "LATE_INSTALLATION_SENSITIVE_TO_OBSERVER_RESOLUTION"
            ),
            "root_cause_status": "UNRESOLVED_PENDING_HIGH_RATE_REPRODUCTION",
            "public_spec_grounded": False,
            "input_digests": {
                "plan": record.plan_digest,
                "trace": record.trace_digest,
                "frozen_evaluation": record.frozen_evaluation_digest,
                "route_observations": file_digest(route_observations_path),
                "processing_result": file_digest(processing_path),
            },
        }
        results.append(result)
        manifest_entry = record.manifest_entry(root)
        manifest_entry.update(
            {
                "route_observations": str(route_observations_path.relative_to(root)),
                "processing_result": str(processing_path.relative_to(root)),
            }
        )
        manifest_entry["digests"].update(
            {
                "route_observations": file_digest(route_observations_path),
                "processing_result": file_digest(processing_path),
            }
        )
        manifest_entries.append(manifest_entry)
    return results, manifest_entries


def _freshness_role(cell_id: str) -> tuple[str, str]:
    if "trajectory-stall" in cell_id:
        return (
            "INJECTED_UPDATE_STARVATION",
            "constant numeric reference; update-starvation response is observable but motion-relative reference divergence is not",
        )
    if "attitude-stall" in cell_id or "body-rate-stall" in cell_id:
        return (
            "INJECTED_RETAINED_COMMAND",
            "retained attitude or rate plus thrust can produce bounded drift",
        )
    if "process-exit" in cell_id:
        return (
            "INJECTED_PROCESS_EXIT",
            "producer exit, health/fallback timing, command age, and recovery are coupled",
        )
    return (
        "INCIDENTAL_THRESHOLD_CROSSING",
        "not an isolated freshness injection; use descriptively only",
    )


def freshness_triage(root: Path) -> list[dict[str, Any]]:
    windows_path = (
        root
        / "experiments/posthoc_physical_execution_validity_v1/aligned-windows.jsonl"
    )
    sensitivity_path = root / "experiments/posthoc_threshold_sensitivity_v1/observations.jsonl"
    maximum_ages = {
        (item["study_id"], item["attempt_id"], int(item["transition_sequence"])): item[
            "value_ns"
        ]
        for item in _read_jsonl(sensitivity_path)
        if item.get("metric_id") == "maximum_command_age_ns"
    }
    results = []
    for window in _read_jsonl(windows_path):
        if (
            window.get("window_kind") != "freshness_exposure"
            or window.get("window_status") != "OBSERVED"
            or window.get("physical_execution_status") != "AIRBORNE"
        ):
            continue
        key = (
            window["study_id"],
            window["attempt_id"],
            int(window["transition_sequence"]),
        )
        role, interpretation = _freshness_role(str(window["cell_id"]))
        metrics = window["physical_metrics"]
        results.append(
            {
                "schema_version": "1.0",
                "study_id": window["study_id"],
                "attempt_id": window["attempt_id"],
                "cell_id": window["cell_id"],
                "setpoint_kind": window["setpoint_kind"],
                "transition_sequence": window["transition_sequence"],
                "exposure_role": role,
                "causal_interpretation": interpretation,
                "maximum_command_age_ns": maximum_ages[key],
                "freshness_window_duration_ns": int(window["end_ns"])
                - int(window["start_ns"]),
                "physical_metrics": {
                    "maximum_distance_from_window_start_m": metrics.get(
                        "maximum_distance_from_window_start_m"
                    ),
                    "horizontal_displacement_m": metrics.get(
                        "horizontal_displacement_m"
                    ),
                    "vertical_displacement_m": metrics.get("vertical_displacement_m"),
                    "peak_horizontal_speed_m_s": metrics.get(
                        "peak_horizontal_speed_m_s"
                    ),
                    "peak_absolute_vertical_speed_m_s": metrics.get(
                        "peak_absolute_vertical_speed_m_s"
                    ),
                    "peak_tilt_deg": metrics.get("peak_tilt_deg"),
                    "peak_body_rate_rad_s": metrics.get("peak_body_rate_rad_s"),
                },
                "enters_a2_hypothesis_selection": role
                in {"INJECTED_UPDATE_STARVATION", "INJECTED_RETAINED_COMMAND"},
            }
        )
    return results


def _closed_dynamic_timeouts(ledger_path: Path) -> list[dict[str, Any]]:
    return [
        value
        for value in _read_jsonl(ledger_path)
        if value.get("state") == "CLOSED"
        and value.get("payload", {}).get("outcome") == "TIMEOUT"
        and "dynamic" in str(value.get("cell_id", ""))
    ]


def dynamic_timeout_triage(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ledger_path = root / "experiments/motivation_thor_v1/attempt-ledger.jsonl"
    timeouts = _closed_dynamic_timeouts(ledger_path)
    results = []
    manifest_entries = []
    for event in timeouts:
        attempt_id = str(event["attempt_id"])
        run_root = root / "runs/motivation-thor-v1" / attempt_id
        paths = {
            "workload_lifecycle": run_root / "raw/workload.lifecycle.jsonl",
            "external_mode_stderr": run_root / "raw/external_mode.stderr.log",
            "requester_stderr": run_root / "raw/external_mode_requester.stderr.log",
            "runtime_result": run_root / "runtime_result.json",
        }
        missing = [path for path in paths.values() if not path.is_file()]
        if missing:
            raise FindingTriageError(
                f"{attempt_id} timeout inputs are missing: {', '.join(map(str, missing))}"
            )
        lifecycle = _read_jsonl(paths["workload_lifecycle"])
        lifecycle_kinds = [str(item.get("kind", "")) for item in lifecycle]
        registration_reply_count = lifecycle_kinds.count("registration_reply")
        cpp_log = paths["external_mode_stderr"].read_text(encoding="utf-8")
        cpp_reply_count = cpp_log.count("Got RegisterExtComponentReply")
        common_signature = (
            lifecycle_kinds == ["requester_started"]
            and cpp_reply_count >= 1
            and registration_reply_count == 0
        )
        results.append(
            {
                "schema_version": "1.0",
                "study_id": "motivation-thor-v1",
                "attempt_id": attempt_id,
                "cell_id": event["cell_id"],
                "ledger_outcome": "TIMEOUT",
                "workload_lifecycle_kinds": lifecycle_kinds,
                "cpp_registration_reply_count": cpp_reply_count,
                "requester_registration_reply_count": registration_reply_count,
                "classification": (
                    "CPP_REGISTERED_REQUESTER_MISSED_READINESS"
                    if common_signature
                    else "DISTINCT_POST_REGISTRATION_TIMEOUT"
                ),
                "exact_dds_root_cause_proven": False,
                "input_digests": {
                    name: file_digest(path) for name, path in paths.items()
                },
            }
        )
        manifest_entries.append(
            {
                "attempt_id": attempt_id,
                "cell_id": event["cell_id"],
                "paths": {name: str(path.relative_to(root)) for name, path in paths.items()},
                "digests": {name: file_digest(path) for name, path in paths.items()},
            }
        )
    requester_source = (
        root
        / "runtime/ros2/family_a_runtime/family_a_runtime/external_mode_requester.py"
    )
    source = requester_source.read_text(encoding="utf-8")
    source_facts = {
        "path": str(requester_source.relative_to(root)),
        "sha256": file_digest(requester_source),
        "subscribes_registration_reply": "/fmu/out/register_ext_component_reply" in source,
        "actions_gate_on_mode_id": (
            "if self._mode_id is None or self._status is None:" in source
        ),
        "readiness_contract_status": "ONE_OBSERVED_REPLY_REQUIRED_NO_RETRY_OR_QUERY",
    }
    return results, manifest_entries, source_facts


def summarize(
    installation: list[dict[str, Any]],
    freshness: list[dict[str, Any]],
    timeouts: list[dict[str, Any]],
) -> dict[str, Any]:
    installation_latencies = [
        int(item["observed_complete_installation_latency_ns"])
        for item in installation
    ]
    lower_bounds = [
        int(
            item["conservative_latency_interval_ns"][
                "lower_after_one_period_and_clock_uncertainty"
            ]
        )
        for item in installation
    ]
    freshness_by_role: dict[str, Any] = {}
    for role in sorted({item["exposure_role"] for item in freshness}):
        selected = [item for item in freshness if item["exposure_role"] == role]
        freshness_by_role[role] = {
            "window_count": len(selected),
            "maximum_command_age_ns": _distribution(
                [int(item["maximum_command_age_ns"]) for item in selected]
            ),
            "maximum_distance_from_window_start_m": _distribution(
                [
                    float(
                        item["physical_metrics"][
                            "maximum_distance_from_window_start_m"
                        ]
                    )
                    for item in selected
                ]
            ),
            "vertical_displacement_m": _distribution(
                [
                    float(item["physical_metrics"]["vertical_displacement_m"])
                    for item in selected
                ]
            ),
        }
    return {
        "schema_version": "1.0",
        "analysis_kind": "read_only_finding_consequence_triage",
        "installation": {
            "violation_trace_count": len(installation),
            "cell_counts": dict(Counter(item["cell_id"] for item in installation)),
            "airborne_trace_count": sum(
                item["physical_execution_status"] == "AIRBORNE"
                for item in installation
            ),
            "setpoint_path": "attitude",
            "observed_latency_ns": _distribution(installation_latencies),
            "conservative_lower_bound_ns": _distribution(lower_bounds),
            "robust_to_one_period_and_clock_count": sum(
                item["definitely_exceeds_deadline_under_interval"]
                for item in installation
            ),
            "observer_profile_counts": dict(
                Counter(
                    str(next(iter(item["observer"]["profile_counts"])))
                    for item in installation
                )
            ),
            "root_cause_status": "UNRESOLVED_PENDING_HIGH_RATE_REPRODUCTION",
            "primary_root_cause_triage_target": True,
        },
        "freshness": {
            "airborne_observed_window_count": len(freshness),
            "role_summaries": freshness_by_role,
            "primary_a2_hypothesis": {
                "fault": "SETPOINT_STALL_HEALTHY",
                "setpoint_semantics": "TIME_VARYING_POSITION_ONLY",
                "motion_context": "CONSTANT_ALTITUDE_STRAIGHT_TRANSLATION",
                "effect": "MOTION_RELATIVE_TRACKING_LAG_AND_RECOVERY",
                "reason": (
                    "Stage A1 already shows a repeatable update-starvation response; "
                    "moving position references separate path-relative lag from the "
                    "constant-reference response"
                ),
            },
        },
        "dynamic_timeouts": {
            "timeout_count": len(timeouts),
            "classification_counts": dict(
                Counter(item["classification"] for item in timeouts)
            ),
            "exact_dds_root_cause_proven": False,
            "blocks_matched_a2_until_qualified": True,
        },
        "claim_boundary": {
            "installation_is_px4_bug": False,
            "freshness_windows_are_independent_defects": False,
            "physical_exposure_is_real_flight_risk_estimate": False,
            "changes_stage_a1_result": False,
        },
    }


def _load_analysis_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "1.0":
        raise FindingTriageError("triage plan must use schema_version 1.0")
    if value.get("analysis_kind") != "read_only_finding_consequence_triage":
        raise FindingTriageError("unexpected triage analysis_kind")
    return value


def _write_new(path: Path, value: str) -> None:
    if path.exists():
        raise FindingTriageError(f"refusing to overwrite triage output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run(root: Path, output_root: Path, analysis_plan_path: Path) -> dict[str, Any]:
    root = root.resolve()
    output_root = output_root.resolve()
    analysis_plan_path = analysis_plan_path.resolve()
    _load_analysis_plan(analysis_plan_path)
    installation, installation_manifest = installation_triage(root)
    freshness = freshness_triage(root)
    timeouts, timeout_manifest, source_facts = dynamic_timeout_triage(root)
    summary = summarize(installation, freshness, timeouts)
    upstream_paths = {
        "physical_execution_manifest": root
        / "experiments/posthoc_physical_execution_validity_v1/input-manifest.json",
        "physical_execution_per_trace": root
        / "experiments/posthoc_physical_execution_validity_v1/per-trace.jsonl",
        "physical_execution_windows": root
        / "experiments/posthoc_physical_execution_validity_v1/aligned-windows.jsonl",
        "physical_execution_summary": root
        / "experiments/posthoc_physical_execution_validity_v1/summary.json",
        "threshold_observations": root
        / "experiments/posthoc_threshold_sensitivity_v1/observations.jsonl",
        "primary_ledger": root / "experiments/motivation_thor_v1/attempt-ledger.jsonl",
    }
    manifest = {
        "schema_version": "1.0",
        "analysis_plan": {
            "path": str(analysis_plan_path.relative_to(root)),
            "sha256": file_digest(analysis_plan_path),
        },
        "upstream_inputs": {
            name: {"path": str(path.relative_to(root)), "sha256": file_digest(path)}
            for name, path in upstream_paths.items()
        },
        "installation_inputs": installation_manifest,
        "dynamic_timeout_inputs": timeout_manifest,
        "requester_source_facts": source_facts,
    }
    _write_new(
        output_root / "installation-triage.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in installation),
    )
    _write_new(
        output_root / "freshness-triage.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in freshness),
    )
    _write_new(
        output_root / "dynamic-timeout-triage.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in timeouts),
    )
    _write_new(
        output_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "input-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--analysis-plan", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.root, args.output_root, args.analysis_plan)
    except (
        CorpusError,
        FindingTriageError,
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
