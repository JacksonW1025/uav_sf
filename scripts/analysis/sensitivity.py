#!/usr/bin/env python3
"""One-factor-at-a-time threshold sensitivity over frozen traces."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics
from typing import Any

from scripts.analysis.corpus import CorpusError, file_digest, load_frozen_corpus
from scripts.analysis.oracle_ablation import evaluate_full_suite_posthoc
from scripts.evaluator.plan import load_plan
from scripts.model.runtime_route import (
    EFFECT_EVENT_KINDS,
    RouteModelError,
    RuntimeRouteInstance,
    read_trace,
)
from scripts.oracles.common import complete_installation
from scripts.oracles.transition_scope import (
    matching_transition_requests,
    transition_window_end_ns,
)


class SensitivityError(RuntimeError):
    """Sensitivity inputs are incomplete or an output would be overwritten."""


def _first_event(
    events: list[dict[str, Any]],
    *,
    kind: str,
    start_ns: int,
    end_ns: int,
    route: str | None = None,
    reasons: set[str] | None = None,
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in sorted(
                events, key=lambda value: (int(value["timestamp_ns"]), int(value["sequence"]))
            )
            if event["kind"] == kind
            and start_ns <= int(event["timestamp_ns"]) <= end_ns
            and (route is None or event.get("route") == route)
            and (reasons is None or str(event.get("reason", "")) in reasons)
        ),
        None,
    )


def extract_transition_metrics(
    events: list[dict[str, Any]],
    plan: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, int | None]:
    """Extract continuous observations without applying a decision threshold."""

    transition = plan["transition"]
    anchor_ns = int(request["timestamp_ns"])
    end_ns = transition_window_end_ns(events, plan, request)
    target = transition["target_route"]
    source = transition["source_route"]
    target_installation = complete_installation(
        events, route=target, anchor_ns=anchor_ns, deadline_ns=end_ns
    )
    installation_latency = (
        int(target_installation["completed_at_ns"]) - anchor_ns
        if target_installation["complete"]
        else None
    )

    source_activations = sorted(
        (
            event
            for event in events
            if event["kind"] == "activation"
            and event.get("route") == source
            and int(event["timestamp_ns"]) <= anchor_ns
        ),
        key=lambda event: (int(event["timestamp_ns"]), int(event["sequence"])),
    )
    source_identity: RuntimeRouteInstance | None = None
    if source_activations:
        try:
            source_identity = RuntimeRouteInstance.from_event(source_activations[-1])
        except RouteModelError:
            source_identity = None
    revocation = next(
        (
            event
            for event in sorted(
                events, key=lambda value: (int(value["timestamp_ns"]), int(value["sequence"]))
            )
            if event["kind"] == "revocation"
            and event.get("route") == source
            and source_identity is not None
            and source_identity.matches(event)
            and anchor_ns <= int(event["timestamp_ns"]) <= end_ns
        ),
        None,
    )
    revocation_latency = (
        int(revocation["timestamp_ns"]) - anchor_ns if revocation is not None else None
    )

    target_write_ns = None
    if target_installation["complete"]:
        target_write_ns = int(
            target_installation["events"]["actuator_write"]["timestamp_ns"]
        )
    source_writes = [
        event
        for event in events
        if event["kind"] == "actuator_write"
        and source_identity is not None
        and source_identity.matches(event)
        and target_write_ns is not None
        and int(event["timestamp_ns"]) <= target_write_ns
    ]
    last_source_ns = max(
        (int(event["timestamp_ns"]) for event in source_writes), default=None
    )
    continuity_gap = (
        target_write_ns - last_source_ns
        if target_write_ns is not None and last_source_ns is not None
        else None
    )

    target_revocation = _first_event(
        events,
        kind="revocation",
        start_ns=anchor_ns,
        end_ns=end_ns,
        route=target,
    )
    authority_end_ns = (
        int(target_revocation["timestamp_ns"])
        if target_revocation is not None
        else end_ns
    )
    ages = [
        int(event["timestamp_ns"]) - int(event["command_subject_ns"])
        for event in events
        if event["kind"] in EFFECT_EVENT_KINDS
        and event.get("route") == target
        and anchor_ns <= int(event["timestamp_ns"]) <= authority_end_ns
        and "command_subject_ns" in event
    ]
    maximum_age = max(ages) if ages else None

    completion = _first_event(
        events,
        kind="completion",
        start_ns=anchor_ns,
        end_ns=end_ns,
        route=target,
    )
    successor_latency = None
    if completion is not None:
        completion_ns = int(completion["timestamp_ns"])
        successor = complete_installation(
            events,
            route=transition["expected_successor"],
            anchor_ns=completion_ns,
            deadline_ns=end_ns,
        )
        if successor["complete"]:
            successor_latency = int(successor["completed_at_ns"]) - completion_ns

    process_exit = _first_event(
        events,
        kind="fault_detected",
        start_ns=anchor_ns,
        end_ns=end_ns,
        reasons={"source_process_exit", "external_component_exit"},
    )
    health_loss = _first_event(
        events,
        kind="fault_detected",
        start_ns=anchor_ns,
        end_ns=end_ns,
        reasons={"external_component_unresponsive"},
    )
    exit_ns = int(process_exit["timestamp_ns"]) if process_exit is not None else None
    fallback_trigger = (
        _first_event(
            events,
            kind="fallback_triggered",
            start_ns=exit_ns,
            end_ns=end_ns,
            route=transition["expected_fallback"],
        )
        if exit_ns is not None
        else None
    )
    fallback_installation = (
        complete_installation(
            events,
            route=transition["expected_fallback"],
            anchor_ns=exit_ns,
            deadline_ns=end_ns,
        )
        if exit_ns is not None
        else {"complete": False}
    )
    proof_loss = _first_event(
        events,
        kind="fault_detected",
        start_ns=anchor_ns,
        end_ns=end_ns,
        reasons={"offboard_proof_of_life_loss", "offboard_signal_lost"},
    )
    return {
        "maximum_command_age_ns": maximum_age,
        "installation_latency_ns": installation_latency,
        "revocation_latency_ns": revocation_latency,
        "continuity_gap_ns": continuity_gap,
        "successor_latency_ns": successor_latency,
        "process_exit_ns": exit_ns,
        "exit_to_health_loss_ns": (
            int(health_loss["timestamp_ns"]) - exit_ns
            if health_loss is not None and exit_ns is not None
            else None
        ),
        "exit_to_fallback_trigger_ns": (
            int(fallback_trigger["timestamp_ns"]) - exit_ns
            if fallback_trigger is not None and exit_ns is not None
            else None
        ),
        "exit_to_fallback_installation_ns": (
            int(fallback_installation["completed_at_ns"]) - exit_ns
            if fallback_installation.get("complete") and exit_ns is not None
            else None
        ),
        "exit_to_offboard_proof_loss_ns": (
            int(proof_loss["timestamp_ns"]) - exit_ns
            if proof_loss is not None and exit_ns is not None
            else None
        ),
    }


def threshold_curve(values: list[int | None], threshold_ns: int) -> dict[str, int]:
    calculable = [value for value in values if value is not None]
    return {
        "threshold_ns": int(threshold_ns),
        "calculable_count": len(calculable),
        "pass_count": sum(int(value) <= threshold_ns for value in calculable),
        "violation_count": sum(int(value) > threshold_ns for value in calculable),
        "unknown_count": sum(value is None for value in values),
    }


def stability_intervals(
    values: list[int | None], minimum_ns: int, maximum_ns: int
) -> list[dict[str, Any]]:
    """Return maximal aggregate-count intervals over a continuous threshold range."""

    calculable = [int(value) for value in values if value is not None]
    boundaries = [minimum_ns]
    boundaries.extend(
        value for value in sorted(set(calculable)) if minimum_ns < value <= maximum_ns
    )
    intervals = []
    for index, lower in enumerate(boundaries):
        upper = boundaries[index + 1] if index + 1 < len(boundaries) else maximum_ns
        point = threshold_curve(values, lower)
        intervals.append(
            {
                "lower_threshold_ns": lower,
                "upper_threshold_ns": upper,
                "lower_inclusive": True,
                "upper_inclusive": index + 1 == len(boundaries),
                "pass_count": point["pass_count"],
                "violation_count": point["violation_count"],
                "unknown_count": point["unknown_count"],
            }
        )
    return intervals


def _grid(start_ms: int, stop_ms: int, step_ms: int) -> list[int]:
    return [value * 1_000_000 for value in range(start_ms, stop_ms + 1, step_ms)]


METRIC_SPECS: dict[str, dict[str, Any]] = {
    "maximum_command_age_ns": {
        "grid": _grid(100, 500, 25),
        "frozen_threshold_ns": 200_000_000,
        "clause": ["freshness_lineage", "freshness"],
    },
    "installation_latency_ns": {
        "grid": _grid(100, 1000, 50),
        "frozen_threshold_ns": 300_000_000,
        "clause": ["route_conformance", "installation"],
    },
    "revocation_latency_ns": {
        "grid": _grid(100, 1000, 50),
        "frozen_threshold_ns": 300_000_000,
        "clause": ["route_conformance", "revocation"],
    },
    "continuity_gap_ns": {
        "grid": _grid(100, 500, 25),
        "frozen_threshold_ns": 250_000_000,
        "clause": ["route_conformance", "continuity"],
    },
    "successor_latency_ns": {
        "grid": _grid(100, 1000, 50),
        "frozen_threshold_ns": 300_000_000,
        "clause": ["successor_progression", "expected_successor"],
    },
    "offboard_exit_to_proof_of_life_loss_ns": {
        "grid": _grid(500, 2000, 50),
        "frozen_threshold_ns": None,
        "clause": None,
    },
    "offboard_exit_to_fallback_trigger_ns": {
        "grid": _grid(500, 2000, 50),
        "frozen_threshold_ns": 1_500_000_000,
        "clause": None,
    },
    "offboard_exit_to_fallback_installation_ns": {
        "grid": _grid(500, 2000, 50),
        "frozen_threshold_ns": 1_500_000_000,
        "clause": ["successor_progression", "safe_fallback"],
    },
    "dynamic_exit_to_health_loss_ns": {
        "grid": _grid(300, 1500, 50),
        "frozen_threshold_ns": None,
        "clause": None,
    },
    "dynamic_exit_to_fallback_trigger_ns": {
        "grid": _grid(500, 2000, 50),
        "frozen_threshold_ns": 1_500_000_000,
        "clause": None,
    },
    "dynamic_exit_to_fallback_installation_ns": {
        "grid": _grid(500, 2000, 50),
        "frozen_threshold_ns": 1_500_000_000,
        "clause": ["successor_progression", "safe_fallback"],
    },
}


def _distribution(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "minimum_ns": ordered[0],
        "median_ns": int(statistics.median(ordered)),
        "p90_nearest_rank_ns": ordered[math.ceil(0.9 * len(ordered)) - 1],
        "maximum_ns": ordered[-1],
    }


def _base_clause_statuses(full: dict[str, Any]) -> dict[tuple[int | None, str, str], str]:
    values: dict[tuple[int | None, str, str], str] = {}
    for instance in full["transition_instances"]:
        sequence = instance["transition_sequence"]
        for oracle in instance["oracles"]:
            for name, clause in oracle["clauses"].items():
                values[(sequence, oracle["oracle"], name)] = clause["status"]
    global_clause = full.get("global_reentry_identity")
    if isinstance(global_clause, dict):
        values[(None, "route_conformance", "reentry_identity")] = global_clause["status"]
    return values


def _overall(statuses: list[str]) -> str:
    if "VIOLATION" in statuses:
        return "VIOLATION"
    if "UNKNOWN" in statuses:
        return "INCONCLUSIVE"
    return "PASS"


def _ofat_trace_counts(
    metric_id: str,
    threshold_ns: int,
    observations: list[dict[str, Any]],
    trace_contexts: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, int] | None:
    clause = METRIC_SPECS[metric_id]["clause"]
    if clause is None:
        return None
    by_trace: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        by_trace[(observation["study_id"], observation["attempt_id"])].append(
            observation
        )
    counts: Counter[str] = Counter()
    for key, candidates in by_trace.items():
        statuses = dict(trace_contexts[key]["clause_statuses"])
        for observation in candidates:
            value = observation["value_ns"]
            replacement = (
                "UNKNOWN"
                if value is None
                else "VIOLATION"
                if int(value) > threshold_ns
                else "PASS"
            )
            statuses[
                (
                    observation["transition_sequence"],
                    str(clause[0]),
                    str(clause[1]),
                )
            ] = replacement
        counts[_overall(list(statuses.values()))] += 1
    return dict(counts)


def _observation(
    *,
    metric_id: str,
    value: int | None,
    record: Any,
    sequence: int,
    mechanism: str,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "metric_id": metric_id,
        "study_id": record.study_id,
        "attempt_id": record.attempt_id,
        "cell_id": record.cell_id,
        "transition_sequence": sequence,
        "mechanism": mechanism,
        "value_ns": value,
        "missing_reason": missing_reason if value is None else None,
    }


def analyze(root: Path) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    observations: list[dict[str, Any]] = []
    contexts: dict[tuple[str, str], dict[str, Any]] = {}
    for record in load_frozen_corpus(root):
        plan = load_plan(record.plan_path)
        events = read_trace(record.trace_path)
        full = evaluate_full_suite_posthoc(events, plan)
        contexts[(record.study_id, record.attempt_id)] = {
            "clause_statuses": _base_clause_statuses(full),
            "full_status": full["status"],
            "oracle_instance_count": len(full["transition_instances"]),
            "not_applicable_instance_count": sum(
                instance["transition_sequence"] is None
                for instance in full["transition_instances"]
            ),
        }
        transition = plan["transition"]
        mechanism = transition["target_route"]
        for request in matching_transition_requests(events, plan):
            sequence = int(request["sequence"])
            metrics = extract_transition_metrics(events, plan, request)
            base_metrics = [
                "maximum_command_age_ns",
                "installation_latency_ns",
                "revocation_latency_ns",
                "continuity_gap_ns",
            ]
            if transition["completion_expected"]:
                base_metrics.append("successor_latency_ns")
            for metric_id in base_metrics:
                value = metrics[metric_id]
                observations.append(
                    _observation(
                        metric_id=metric_id,
                        value=value,
                        record=record,
                        sequence=sequence,
                        mechanism=mechanism,
                        missing_reason="continuous observation is unavailable",
                    )
                )
            is_process_exit = "process-exit" in record.cell_id
            if not is_process_exit:
                continue
            if mechanism == "legacy_offboard":
                names = {
                    "offboard_exit_to_proof_of_life_loss_ns": "exit_to_offboard_proof_loss_ns",
                    "offboard_exit_to_fallback_trigger_ns": "exit_to_fallback_trigger_ns",
                    "offboard_exit_to_fallback_installation_ns": "exit_to_fallback_installation_ns",
                }
            elif mechanism == "dynamic_external_mode":
                names = {
                    "dynamic_exit_to_health_loss_ns": "exit_to_health_loss_ns",
                    "dynamic_exit_to_fallback_trigger_ns": "exit_to_fallback_trigger_ns",
                    "dynamic_exit_to_fallback_installation_ns": "exit_to_fallback_installation_ns",
                }
            else:
                names = {}
            for metric_id, source_name in names.items():
                value = metrics[source_name]
                observations.append(
                    _observation(
                        metric_id=metric_id,
                        value=value,
                        record=record,
                        sequence=sequence,
                        mechanism=mechanism,
                        missing_reason=(
                            "required mechanism-specific event is absent from the frozen trace"
                        ),
                    )
                )
    return observations, contexts


def build_curves(
    observations: list[dict[str, Any]],
    contexts: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for metric_id, spec in METRIC_SPECS.items():
        selected = [item for item in observations if item["metric_id"] == metric_id]
        values = [item["value_ns"] for item in selected]
        calculable = [int(value) for value in values if value is not None]
        regular_grid = []
        for threshold in spec["grid"]:
            point: dict[str, Any] = threshold_curve(values, threshold)
            point["ofat_trace_status_counts"] = _ofat_trace_counts(
                metric_id, threshold, selected, contexts
            )
            regular_grid.append(point)
        crossing_points = []
        for threshold in sorted(set(calculable)):
            point = threshold_curve(values, threshold)
            point["ofat_trace_status_counts"] = _ofat_trace_counts(
                metric_id, threshold, selected, contexts
            )
            crossing_points.append(point)
        minimum = min(spec["grid"])
        maximum = max(spec["grid"])
        frozen = spec["frozen_threshold_ns"]
        next_looser = next(
            (threshold for threshold in spec["grid"] if frozen is not None and threshold > frozen),
            None,
        )
        local_crossings = []
        if frozen is not None and next_looser is not None:
            local_crossings = [
                {
                    "study_id": item["study_id"],
                    "attempt_id": item["attempt_id"],
                    "transition_sequence": item["transition_sequence"],
                    "value_ns": item["value_ns"],
                }
                for item in selected
                if item["value_ns"] is not None
                and frozen < int(item["value_ns"]) <= next_looser
            ]
        metrics[metric_id] = {
            "applicable_observation_count": len(selected),
            "calculable_count": len(calculable),
            "missing_or_unknown_count": len(selected) - len(calculable),
            "frozen_threshold_ns": frozen,
            "frozen_threshold_status": (
                "REGISTERED_FORMAL_BOUND" if frozen is not None else "NOT_PREREGISTERED"
            ),
            "distribution": _distribution(calculable),
            "reasonable_grid_ns": spec["grid"],
            "regular_grid_curve": regular_grid,
            "observed_crossing_curve": crossing_points,
            "aggregate_stability_intervals": stability_intervals(
                values, minimum, maximum
            ),
            "verdict_stability": {
                "stable_pass_across_grid": sum(value <= minimum for value in calculable),
                "stable_violation_across_grid": sum(value > maximum for value in calculable),
                "threshold_dependent_within_grid": sum(
                    minimum < value <= maximum for value in calculable
                ),
                "unknown_across_grid": len(selected) - len(calculable),
            },
            "frozen_local_crossings": local_crossings,
            "ofat": True,
        }
    return {
        "schema_version": "1.0",
        "analysis_kind": "read_only_one_factor_at_a_time_sensitivity",
        "metric_count": len(metrics),
        "metrics": metrics,
    }


def summarize(
    curves: dict[str, Any],
    observations: list[dict[str, Any]],
    contexts: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    transition_instance_count = len(
        {
            (item["study_id"], item["attempt_id"], item["transition_sequence"])
            for item in observations
            if item["metric_id"] == "installation_latency_ns"
        }
    )
    return {
        "schema_version": "1.0",
        "analysis_kind": curves["analysis_kind"],
        "input_trace_count": 151,
        "oracle_instance_count": sum(
            context["oracle_instance_count"] for context in contexts.values()
        ),
        "transition_instance_count": transition_instance_count,
        "not_applicable_instance_count": sum(
            context["not_applicable_instance_count"] for context in contexts.values()
        ),
        "trace_with_continuous_observation_count": len(
            {
                (item["study_id"], item["attempt_id"])
                for item in observations
                if item["metric_id"] == "installation_latency_ns"
            }
        ),
        "metric_summaries": {
            metric_id: {
                "applicable_observation_count": value["applicable_observation_count"],
                "calculable_count": value["calculable_count"],
                "missing_or_unknown_count": value["missing_or_unknown_count"],
                "frozen_threshold_ns": value["frozen_threshold_ns"],
                "distribution": value["distribution"],
                "verdict_stability": value["verdict_stability"],
                "frozen_local_crossing_count": len(value["frozen_local_crossings"]),
            }
            for metric_id, value in curves["metrics"].items()
        },
        "interpretation": {
            "changes_frozen_verdict": False,
            "default_analysis": "one_factor_at_a_time",
            "missing_values_are_interpolated": False,
            "dynamic_fallback_uses_com_of_loss_t": False,
        },
    }


def _write_new(path: Path, value: str) -> None:
    if path.exists():
        raise SensitivityError(f"refusing to overwrite sensitivity output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run(root: Path, output_root: Path) -> dict[str, Any]:
    root = root.resolve()
    output_root = output_root.resolve()
    observations, contexts = analyze(root)
    curves = build_curves(observations, contexts)
    summary = summarize(curves, observations, contexts)
    _write_new(
        output_root / "observations.jsonl",
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in observations),
    )
    _write_new(
        output_root / "curves.json",
        json.dumps(curves, indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    manifest = {
        "schema_version": "1.0",
        "frozen_inputs": [record.manifest_entry(root) for record in load_frozen_corpus(root)],
        "analysis_inputs": {
            "ablation_summary": {
                "path": "experiments/posthoc_oracle_ablation_v1/summary.json",
                "sha256": file_digest(
                    root / "experiments/posthoc_oracle_ablation_v1/summary.json"
                ),
            }
        },
    }
    _write_new(
        output_root / "input-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.root, args.output_root)
    except (SensitivityError, CorpusError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
