#!/usr/bin/env python3
"""Run same-trace observation-model ablation over frozen Motivation evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.analysis.corpus import CorpusError, file_digest, load_frozen_corpus
from scripts.evaluator.evaluate_trace import evaluate
from scripts.evaluator.plan import load_plan
from scripts.evaluator.result_model import load_evaluation
from scripts.model.runtime_route import read_trace
from scripts.oracles.route_conformance import evaluate_route_conformance
from scripts.oracles.transition_scope import (
    matching_transition_requests,
    transition_window_end_ns,
)


MODE_LABELS = {
    "px4_internal": "PX4_INTERNAL",
    "internal_hold": "HOLD",
    "internal_rtl": "RTL",
    "internal_land": "LAND",
    "internal_recovery": "RECOVERY",
    "legacy_offboard": "OFFBOARD",
    "dynamic_external_mode": "EXTERNAL_MODE",
    "mode_executor": "EXECUTOR_OWNED_MODE",
}
SAFUZZ_SOURCE = {
    "title": (
        "Uncovering Failures in Cyber-Physical System State Transitions: "
        "A Fuzzing-Based Approach Applied to sUAS"
    ),
    "method_name": "SaFUZZ",
    "version": "arXiv v1 author-accepted manuscript, 2026-01-09",
    "pdf_url": "https://arxiv.org/pdf/2601.05449",
    "pdf_sha256": "sha256:0c14b142e8382e65a3dbdef77298ecd63fa72fa5d9ee2e70e35f022c616dd702",
    "supplement_url": "https://github.com/SAREC-Lab/saFUZZ_ICSE26",
    "supplement_commit": "4e0d08b4a6ec5cde245311e52d249fdf8fc7a780",
    "accessed_on": "2026-08-14",
}


class AblationError(RuntimeError):
    """The post-hoc analysis cannot be completed without guessing."""


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _project_status(raw: str) -> str:
    return {
        "Passing": "PASS",
        "Failing": "VIOLATION",
        "Invalid": "INCONCLUSIVE",
        "Unknown": "INCONCLUSIVE",
        "NotApplicable": "INCONCLUSIVE",
    }[raw]


def _mode(route: object) -> str:
    return MODE_LABELS.get(str(route), "UNKNOWN_MODE")


def _mode_projection(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sequence": int(event["sequence"]),
            "timestamp_ns": int(event["timestamp_ns"]),
            "mode": _mode(event.get("route")),
        }
        for event in events
        if event["kind"] == "activation"
    ]


def _activation_in_window(
    mode_events: list[dict[str, Any]], target: str, start_ns: int, end_ns: int
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in mode_events
            if event["mode"] == target
            and start_ns <= int(event["timestamp_ns"]) <= end_ns
        ),
        None,
    )


def evaluate_mode_only(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate only requested and declared application/PX4 mode changes."""

    transition = plan["transition"]
    requests = matching_transition_requests(events, plan)
    modes = _mode_projection(events)
    target = _mode(transition["target_route"])
    observed: list[dict[str, Any]] = []
    for request in requests:
        end_ns = transition_window_end_ns(events, plan, request)
        activation = _activation_in_window(
            modes, target, int(request["timestamp_ns"]), end_ns
        )
        observed.append(
            {
                "request_sequence": int(request["sequence"]),
                "target_mode": target,
                "activation_sequence": (
                    int(activation["sequence"]) if activation is not None else None
                ),
            }
        )
    if not transition["target_activation_expected"]:
        raw = "Failing" if any(item["activation_sequence"] for item in observed) else "Unknown"
        reasons = [
            "mode-only evidence cannot prove why a requested activation was rejected"
        ]
    elif not requests:
        raw = "Unknown"
        reasons = ["the planned mode request was not observed"]
    else:
        low, high = map(int, transition["target_activation_count"])
        activated = sum(item["activation_sequence"] is not None for item in observed)
        raw = "Passing" if low <= activated <= high and activated == len(requests) else "Failing"
        reasons = [] if raw == "Passing" else ["declared target mode did not follow every request"]
    return {
        "layer": "mode_only",
        "raw_verdict": raw,
        "status": _project_status(raw),
        "reasons": reasons,
        "evidence": {"transitions": observed},
        "observation_fields": ["application_state", "declared_mode", "request_time"],
        "observation_event_count": len(requests) + len(modes),
        "observation_stage_count": 1,
    }


def evaluate_terminal_only(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate only the final landed/disarmed observation."""

    terminal = next(
        (event for event in reversed(events) if event["kind"] == "terminal_state"),
        None,
    )
    if terminal is None:
        raw = "Unknown"
        reasons = ["terminal state observation is missing"]
        evidence: dict[str, Any] = {}
    else:
        landed = bool(terminal.get("landed"))
        disarmed = bool(terminal.get("disarmed"))
        cleanup = plan["cleanup"]
        passed = (not cleanup["require_landed"] or landed) and (
            not cleanup["require_disarmed"] or disarmed
        )
        raw = "Passing" if passed else "Failing"
        reasons = [] if passed else ["required terminal outcome was not reached"]
        evidence = {
            "terminal_sequence": int(terminal["sequence"]),
            "landed": landed,
            "disarmed": disarmed,
        }
    return {
        "layer": "terminal_only",
        "raw_verdict": raw,
        "status": _project_status(raw),
        "reasons": reasons,
        "evidence": evidence,
        "observation_fields": ["landed", "disarmed", "mission_completion"],
        "observation_event_count": 0 if terminal is None else 1,
        "observation_stage_count": 1,
    }


def evaluate_safuzz_adaptation(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    """Adapt the published SuT-level decision-tree observation model only."""

    transition = plan["transition"]
    requests = matching_transition_requests(events, plan)
    modes = _mode_projection(events)
    target_mode = _mode(transition["target_route"])
    projected_events = [
        event
        for event in events
        if event["kind"]
        in {
            "completion",
            "fault_detected",
            "fallback_triggered",
            "adjacent_request",
            "terminal_state",
        }
    ]
    terminal = next(
        (event for event in reversed(events) if event["kind"] == "terminal_state"),
        None,
    )
    if not transition["target_activation_expected"]:
        raw = "Unknown"
        reasons = [
            "published decision-tree predicates do not establish registration or activation rejection"
        ]
    elif not requests:
        raw = "Invalid"
        reasons = ["target state/mode precondition did not occur"]
    else:
        raw = "Passing"
        reasons = []
        for request in requests:
            start_ns = int(request["timestamp_ns"])
            end_ns = transition_window_end_ns(events, plan, request)
            target_activation = _activation_in_window(
                modes, target_mode, start_ns, end_ns
            )
            if target_activation is None:
                raw = "Invalid"
                reasons.append("target state/mode precondition did not occur")
                break
            completion = next(
                (
                    event
                    for event in projected_events
                    if event["kind"] == "completion"
                    and start_ns <= int(event["timestamp_ns"]) <= end_ns
                ),
                None,
            )
            fault = next(
                (
                    event
                    for event in projected_events
                    if event["kind"] == "fault_detected"
                    and start_ns <= int(event["timestamp_ns"]) <= end_ns
                ),
                None,
            )
            anchor_ns = start_ns
            expected_mode: str | None = None
            if transition["fault_expected"]:
                if fault is None:
                    raw = "Invalid"
                    reasons.append("planned injected fault was not observed in its target context")
                    break
                anchor_ns = int(fault["timestamp_ns"])
                if transition["fallback_expected"]:
                    expected_mode = _mode(transition["expected_fallback"])
            elif transition["completion_expected"]:
                if completion is None:
                    raw = "Failing"
                    reasons.append("mission completion condition was not reached")
                    break
                anchor_ns = int(completion["timestamp_ns"])
                expected_mode = _mode(transition["expected_successor"])
            if expected_mode is not None and _activation_in_window(
                modes, expected_mode, anchor_ns, end_ns
            ) is None:
                raw = "Failing"
                reasons.append("expected mode/failsafe successor was not observed")
                break
        if raw == "Passing" and terminal is None:
            raw = "Unknown"
            reasons.append("terminal mission observation is missing")
        elif raw == "Passing" and terminal is not None:
            cleanup = plan["cleanup"]
            if (cleanup["require_landed"] and not bool(terminal.get("landed"))) or (
                cleanup["require_disarmed"] and not bool(terminal.get("disarmed"))
            ):
                raw = "Failing"
                reasons.append("terminal mission success criteria were not satisfied")
    return {
        "layer": "safuzz_published_model_adaptation",
        "adaptation_id": "SAFUZZ_PUBLISHED_MODEL_ADAPTATION",
        "raw_verdict": raw,
        "status": _project_status(raw),
        "reasons": reasons,
        "evidence": {
            "target_mode": target_mode,
            "mode_sequence": [event["mode"] for event in modes],
            "completion_observed": any(
                event["kind"] == "completion" for event in projected_events
            ),
            "failsafe_observed": any(
                event["kind"] in {"fault_detected", "fallback_triggered"}
                for event in projected_events
            ),
            "terminal_observed": terminal is not None,
        },
        "predicate_provenance": {
            "published": [
                "target state/mode precondition",
                "mode and failsafe successor",
                "mission completion",
                "landed terminal outcome",
            ],
            "family_a_mapping": [
                "PX4 mode labels projected from normalized activation observations",
                "registered expected successor/fallback projected to a mode label",
            ],
            "not_observable_in_corpus": [
                "planned-path deviation",
                "home-coordinate landing distance",
                "mission-duration significance",
                "kill-switch spatial predicate",
            ],
        },
        "observation_fields": [
            "application_state",
            "declared_mode",
            "failsafe_state",
            "human_mode_request",
            "mission_completion",
            "landed",
            "disarmed",
        ],
        "observation_event_count": len(requests) + len(modes) + len(projected_events),
        "observation_stage_count": 3,
    }


def evaluate_full_suite_posthoc(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate each repeated request independently while preserving the frozen result."""

    requests = matching_transition_requests(events, plan)
    if len(requests) <= 1:
        result = evaluate(events, plan)
        sequence = int(requests[0]["sequence"]) if requests else None
        return {
            "layer": "full_oracle_posthoc",
            "status": result["status"],
            "semantic_disposition": result["semantic_disposition"],
            "findings": result["findings"],
            "evidence_gate": result["evidence_gate"],
            "transition_instances": [
                {
                    "transition_sequence": sequence,
                    "status": result["status"],
                    "semantic_disposition": result["semantic_disposition"],
                    "findings": result["findings"],
                    "oracles": result["oracles"],
                }
            ],
            "global_reentry_identity": None,
            "observation_fields": [
                "route_epoch",
                "producer_session",
                "registration_id",
                "activation_id",
                "command_subject_ns",
                "controller_id",
                "allocator_id",
                "writer_id",
                "lifecycle_owner",
                "executor_owner",
                "successor",
                "fallback",
            ],
            "observation_event_count": len(events),
            "observation_stage_count": 6,
        }

    instances: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    dispositions: set[str] = set()
    for request in requests:
        instance_plan = deepcopy(plan)
        instance_plan["_analysis_transition_sequence"] = int(request["sequence"])
        instance_plan["transition"]["target_activation_count"] = [1, 1]
        result = evaluate(events, instance_plan)
        instance_findings = []
        for finding in result["findings"]:
            scoped = deepcopy(finding)
            scoped["transition_sequence"] = int(request["sequence"])
            instance_findings.append(scoped)
            findings.append(scoped)
        dispositions.update(result["semantic_disposition"]["all"])
        instances.append(
            {
                "transition_sequence": int(request["sequence"]),
                "status": result["status"],
                "semantic_disposition": result["semantic_disposition"],
                "findings": instance_findings,
                "oracles": result["oracles"],
            }
        )
    global_reentry = evaluate_route_conformance(events, plan)["clauses"][
        "reentry_identity"
    ]
    if global_reentry["status"] == "VIOLATION":
        finding = {
            "finding_id": _digest(
                {
                    "oracle": "route_conformance",
                    "clause": "reentry_identity",
                    "evidence": global_reentry.get("evidence", {}),
                }
            ),
            "oracle": "route_conformance",
            "clause": "reentry_identity",
            "clause_status": "VIOLATION",
            "semantic_disposition": "SAFETY_CONTRACT_VIOLATION",
            "contract_provenance": {
                "kind": "RESEARCH_SAFETY_CONTRACT",
                "source": "preregistered experiment plan",
                "public_spec_reference": None,
                "threshold_field": None,
            },
            "classifications": [
                "RESEARCH_SAFETY_CONTRACT",
                "SAFETY_RELEVANT_EXPOSURE",
            ],
            "reasons": global_reentry.get("reasons", []),
            "evidence": global_reentry.get("evidence", {}),
            "transition_sequence": None,
        }
        findings.append(finding)
        dispositions.add("SAFETY_CONTRACT_VIOLATION")
    statuses = [instance["status"] for instance in instances]
    if "VIOLATION" in statuses or global_reentry["status"] == "VIOLATION":
        status = "VIOLATION"
    elif "INCONCLUSIVE" in statuses or global_reentry["status"] == "UNKNOWN":
        status = "INCONCLUSIVE"
    else:
        status = "PASS"
    if status == "PASS":
        dispositions = {"PASS"}
    elif status == "INCONCLUSIVE":
        dispositions.add("UNKNOWN")
    order = {
        "SPEC_VIOLATION": 0,
        "SAFETY_CONTRACT_VIOLATION": 1,
        "DIFFERENTIAL_DIVERGENCE": 2,
        "UNKNOWN": 3,
        "PASS": 4,
        "NOT_APPLICABLE": 5,
    }
    all_dispositions = sorted(dispositions, key=order.__getitem__)
    return {
        "layer": "full_oracle_posthoc",
        "status": status,
        "semantic_disposition": {
            "primary": all_dispositions[0],
            "all": all_dispositions,
        },
        "findings": findings,
        "evidence_gate": instances[0]["oracles"] and evaluate(events, plan)[
            "evidence_gate"
        ],
        "transition_instances": instances,
        "global_reentry_identity": global_reentry,
        "observation_fields": [
            "route_epoch",
            "producer_session",
            "registration_id",
            "activation_id",
            "command_subject_ns",
            "controller_id",
            "allocator_id",
            "writer_id",
            "lifecycle_owner",
            "executor_owner",
            "successor",
            "fallback",
        ],
        "observation_event_count": len(events),
        "observation_stage_count": 6,
    }


def _finding_cluster_key(finding: dict[str, Any]) -> str:
    return _digest(
        {
            "oracle": finding.get("oracle"),
            "clause": finding.get("clause"),
            "reasons": finding.get("reasons", []),
            "classifications": finding.get("classifications", []),
        }
    )


def _status_counts(results: list[dict[str, Any]], layer: str) -> dict[str, int]:
    return dict(Counter(result["layers"][layer]["status"] for result in results))


def analyze_record(record: Any) -> dict[str, Any]:
    plan = load_plan(record.plan_path)
    events = read_trace(record.trace_path)
    frozen = load_evaluation(record.frozen_evaluation_path)
    layers = {
        "frozen_formal": {
            "layer": "frozen_formal",
            "status": frozen["status"],
            "schema_version": frozen["schema_version"],
            "observation_fields": ["frozen_evaluation"],
            "observation_event_count": len(events),
            "observation_stage_count": 6,
        },
        "mode_only": evaluate_mode_only(events, plan),
        "terminal_only": evaluate_terminal_only(events, plan),
        "safuzz_adaptation": evaluate_safuzz_adaptation(events, plan),
        "full_oracle_posthoc": evaluate_full_suite_posthoc(events, plan),
    }
    full = layers["full_oracle_posthoc"]
    relative_missed: dict[str, list[str]] = {}
    for baseline in ("mode_only", "terminal_only", "safuzz_adaptation"):
        if layers[baseline]["status"] == "PASS" and full["status"] == "VIOLATION":
            relative_missed[baseline] = [
                str(finding["finding_id"]) for finding in full["findings"]
            ]
        else:
            relative_missed[baseline] = []
    return {
        "schema_version": "1.0",
        "study_id": record.study_id,
        "attempt_id": record.attempt_id,
        "cell_id": record.cell_id,
        "input_digests": {
            "plan": record.plan_digest,
            "trace": record.trace_digest,
            "frozen_evaluation": record.frozen_evaluation_digest,
        },
        "event_count": len(events),
        "layers": layers,
        "relative_missed_findings": relative_missed,
        "compatibility_delta": {
            "changed": frozen["status"] != full["status"],
            "frozen_status": frozen["status"],
            "posthoc_status": full["status"],
        },
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    layer_names = (
        "frozen_formal",
        "mode_only",
        "terminal_only",
        "safuzz_adaptation",
        "full_oracle_posthoc",
    )
    overlap: dict[str, dict[str, int]] = {}
    for baseline in ("mode_only", "terminal_only", "safuzz_adaptation"):
        overlap[baseline] = dict(
            Counter(
                f"{result['layers'][baseline]['status']}->{result['layers']['full_oracle_posthoc']['status']}"
                for result in results
            )
        )
    cluster_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    classification_counts: Counter[str] = Counter(
        {
            "PUBLIC_SPEC_GROUNDED": 0,
            "RESEARCH_SAFETY_CONTRACT": 0,
            "SAFETY_RELEVANT_EXPOSURE": 0,
            "SOFTWARE_OR_DIAGNOSTIC_ANOMALY": 0,
            "THRESHOLD_SENSITIVE_ANOMALY": 0,
            "POSSIBLE_EXPERIMENT_OR_ORACLE_ARTIFACT": 0,
        }
    )
    semantic_counts: Counter[str] = Counter()
    for result in results:
        for finding in result["layers"]["full_oracle_posthoc"]["findings"]:
            cluster_members[_finding_cluster_key(finding)].append(
                {"result": result, "finding": finding}
            )
            classification_counts.update(finding.get("classifications", []))
            semantic_counts.update([str(finding.get("semantic_disposition", "UNKNOWN"))])
    clusters = []
    for cluster_id, members in sorted(cluster_members.items()):
        representative = min(members, key=lambda item: item["result"]["event_count"])
        finding = representative["finding"]
        clusters.append(
            {
                "cluster_id": cluster_id,
                "oracle": finding.get("oracle"),
                "clause": finding.get("clause"),
                "reasons": finding.get("reasons", []),
                "trace_count": len(members),
                "representative_smallest_observed_trace": {
                    "study_id": representative["result"]["study_id"],
                    "attempt_id": representative["result"]["attempt_id"],
                    "event_count": representative["result"]["event_count"],
                },
                "claim_boundary": "signature cluster, not an independent software defect",
            }
        )
    return {
        "schema_version": "1.0",
        "analysis_kind": "read_only_posthoc_oracle_ablation",
        "input_trace_count": len(results),
        "study_counts": dict(Counter(result["study_id"] for result in results)),
        "layer_status_counts": {
            layer: _status_counts(results, layer) for layer in layer_names
        },
        "detection_overlap_relative_to_posthoc_full": overlap,
        "relative_missed_finding_trace_counts": {
            baseline: sum(
                bool(result["relative_missed_findings"][baseline]) for result in results
            )
            for baseline in ("mode_only", "terminal_only", "safuzz_adaptation")
        },
        "compatibility_delta_count": sum(
            bool(result["compatibility_delta"]["changed"]) for result in results
        ),
        "finding_classification_counts": dict(classification_counts),
        "finding_semantic_disposition_counts": dict(semantic_counts),
        "finding_signature_cluster_count": len(clusters),
        "finding_signature_clusters": clusters,
        "ground_truth_boundary": (
            "baseline-undetected post-hoc findings are relative missed findings; "
            "they are not labelled false negatives without independent ground truth"
        ),
        "issue_localization": {
            "status": "NOT_EVALUATED_ON_ISSUE_LABELLED_TRACES",
            "reason": (
                "the frozen Motivation corpus has no issue-specific ground-truth labels; "
                "capability is not inferred from shared symptoms"
            ),
        },
        "observation_cost": {
            layer: {
                "observation_fields": results[0]["layers"][layer][
                    "observation_fields"
                ],
                "field_count": len(
                    results[0]["layers"][layer]["observation_fields"]
                ),
                "total_observed_events": sum(
                    int(result["layers"][layer]["observation_event_count"])
                    for result in results
                ),
                "mean_observed_events_per_trace": round(
                    sum(
                        int(result["layers"][layer]["observation_event_count"])
                        for result in results
                    )
                    / len(results),
                    3,
                ),
                "observation_stage_count": results[0]["layers"][layer][
                    "observation_stage_count"
                ],
            }
            for layer in ("mode_only", "terminal_only", "safuzz_adaptation", "full_oracle_posthoc")
        },
        "safuzz_source": SAFUZZ_SOURCE,
    }


def _write_new(path: Path, text: str) -> None:
    if path.exists():
        raise AblationError(f"refusing to overwrite analysis output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(root: Path, output_root: Path) -> dict[str, Any]:
    root = root.resolve()
    output_root = output_root.resolve()
    records = load_frozen_corpus(root)
    results = [analyze_record(record) for record in records]
    summary = summarize(results)
    manifest = {
        "schema_version": "1.0",
        "input_count": len(records),
        "entries": [record.manifest_entry(root) for record in records],
        "frozen_study_digests": {
            "primary_matrix": file_digest(
                root / "experiments/motivation_thor_v1/matrix.json"
            ),
            "primary_ledger": file_digest(
                root / "experiments/motivation_thor_v1/attempt-ledger.jsonl"
            ),
            "supplemental_matrix": file_digest(
                root / "experiments/motivation_thor_remediation_v1/matrix.json"
            ),
            "supplemental_ledger": file_digest(
                root
                / "experiments/motivation_thor_remediation_v1/attempt-ledger.jsonl"
            ),
        },
    }
    _write_new(
        output_root / "input-manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    _write_new(
        output_root / "per-trace.jsonl",
        "".join(json.dumps(result, sort_keys=True) + "\n" for result in results),
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
    args = parser.parse_args()
    try:
        summary = run(args.root, args.output_root)
    except (AblationError, CorpusError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": "PASS", "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
