#!/usr/bin/env python3
"""Evaluate stale external-command exposure before PX4 route revocation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
RESULT_SCHEMA_PATH = ROOT / "data" / "schemas" / "pre_revocation_freshness_result.schema.json"
STATUSES = {"PASS", "EXPOSURE", "VIOLATION", "UNKNOWN", "NOT_APPLICABLE"}
CLAUSE_NAMES = (
    "producer_cessation",
    "setpoint_freshness",
    "controller_continuation",
    "allocator_writer_continuation",
    "fallback_detection",
    "fallback_installation",
    "physical_consequence",
    "recovery",
)


def _clause(
    status: str,
    *reasons: str,
    evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    if status not in STATUSES:
        raise ValueError(f"invalid clause status: {status}")
    return {"status": status, "reasons": list(reasons), "evidence": evidence or {}}


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _timestamp(observation: dict[str, Any], name: str) -> float | None:
    timestamps = observation.get("timestamps_us")
    if not isinstance(timestamps, dict):
        return None
    return _number(timestamps.get(name))


def _window_complete(observation: dict[str, Any], name: str) -> bool:
    windows = observation.get("windows")
    return isinstance(windows, dict) and windows.get(name) == "COMPLETE"


def _duration_ms(end_us: float | None, start_us: float | None) -> float | None:
    if end_us is None or start_us is None:
        return None
    return (end_us - start_us) / 1000.0


def _not_applicable(profile: dict[str, Any], observation: dict[str, Any], reason: str) -> dict[str, Any]:
    clauses = {name: _clause("NOT_APPLICABLE", reason) for name in CLAUSE_NAMES}
    return _result(profile, observation, clauses, [], {}, False, reason)


def evaluate(profile: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one already-collected run against a frozen freshness profile."""

    if profile.get("applicability") == "NOT_APPLICABLE":
        return _not_applicable(profile, observation, "profile is explicitly not applicable")

    fault_type = str(observation.get("fault_type", ""))
    producer_stopped = observation.get("producer_stopped")
    if producer_stopped is False:
        return _not_applicable(
            profile,
            observation,
            "setpoint production continued, so no producer-cessation freshness window exists",
        )

    environment = str(observation.get("environment_status", "UNKNOWN"))
    if environment != "VALID":
        reason = f"run excluded from SUT adjudication: environment_status={environment}"
        clauses = {name: _clause("UNKNOWN", reason) for name in CLAUSE_NAMES}
        return _result(
            profile,
            observation,
            clauses,
            [environment],
            {},
            False,
            environment,
        )

    clock_bridge_status = str(observation.get("clock_bridge_status", "UNKNOWN"))
    if clock_bridge_status != "VALID":
        reason = f"cross-domain clock bridge is not valid: {clock_bridge_status}"
        clauses = {name: _clause("UNKNOWN", reason) for name in CLAUSE_NAMES}
        return _result(
            profile,
            observation,
            clauses,
            ["CLOCK_BRIDGE_INVALID"],
            {},
            False,
            "MEASUREMENT_UNKNOWN",
        )

    fault = _timestamp(observation, "fault_injection")
    producer_last = _timestamp(observation, "producer_last_publish")
    px4_receive = _timestamp(observation, "px4_last_setpoint_receive")
    last_consumption = _timestamp(observation, "last_setpoint_consumption")
    last_allocator = _timestamp(observation, "last_external_allocator_input")
    last_writer = _timestamp(observation, "last_external_writer_output")
    health_loss = _timestamp(observation, "health_loss_detection")
    fallback_declared = _timestamp(observation, "fallback_declared")
    fallback_installed = _timestamp(observation, "fallback_installed")
    recovery_time = _timestamp(observation, "physical_recovery")

    policy = profile.get("policy") if isinstance(profile.get("policy"), dict) else {}
    freshness_kind = str(policy.get("freshness", "NONE"))
    timeout_ms = _number(policy.get("setpoint_timeout_ms"))
    measurement_tolerance_ms = _number(policy.get("measurement_tolerance_ms")) or 0.0
    publish_grace_ms = _number(policy.get("max_publish_after_fault_ms")) or 0.0
    route_grace_ms = _number(policy.get("post_fallback_external_effect_grace_ms")) or 0.0
    categories: list[str] = []
    clauses: dict[str, dict[str, object]] = {}

    if not _window_complete(observation, "pre_fault_stable"):
        clauses["producer_cessation"] = _clause(
            "UNKNOWN", "pre-fault stable baseline window is incomplete"
        )
    elif fault is None or producer_last is None or producer_stopped is not True:
        clauses["producer_cessation"] = _clause(
            "UNKNOWN", "fault marker or producer last-publish/cessation evidence is missing"
        )
    else:
        publish_after_fault_ms = _duration_ms(producer_last, fault)
        assert publish_after_fault_ms is not None
        if publish_after_fault_ms > publish_grace_ms:
            clauses["producer_cessation"] = _clause(
                "VIOLATION",
                "producer continued publishing beyond the preregistered cessation grace",
                evidence={"publish_after_fault_ms": publish_after_fault_ms},
            )
            categories.append("PRODUCER_CESSATION_DEADLINE_EXCEEDED")
        else:
            clauses["producer_cessation"] = _clause(
                "PASS", evidence={"publish_after_fault_ms": publish_after_fault_ms}
            )

    target_complete = _window_complete(observation, "pre_revocation_target")
    stale_consumption_ms = _duration_ms(last_consumption, px4_receive)
    if px4_receive is None:
        clauses["setpoint_freshness"] = _clause(
            "UNKNOWN", "PX4 last-setpoint receive timestamp is missing"
        )
    elif last_consumption is None:
        clauses["setpoint_freshness"] = _clause(
            "UNKNOWN", "controller consumption timestamp is missing"
        )
    elif not target_complete:
        clauses["setpoint_freshness"] = _clause(
            "UNKNOWN", "pre-revocation target window is incomplete"
        )
    elif freshness_kind == "EXPLICIT" and timeout_ms is not None:
        assert stale_consumption_ms is not None
        if stale_consumption_ms > timeout_ms + measurement_tolerance_ms:
            clauses["setpoint_freshness"] = _clause(
                "VIOLATION",
                "setpoint was consumed after the explicit freshness deadline",
                evidence={
                    "stale_consumption_ms": stale_consumption_ms,
                    "timeout_ms": timeout_ms,
                    "measurement_tolerance_ms": measurement_tolerance_ms,
                },
            )
            categories.append("SETPOINT_POLICY_DEADLINE_EXCEEDED")
        else:
            clauses["setpoint_freshness"] = _clause(
                "PASS",
                evidence={"stale_consumption_ms": stale_consumption_ms, "timeout_ms": timeout_ms},
            )
    else:
        assert stale_consumption_ms is not None
        if stale_consumption_ms > measurement_tolerance_ms:
            clauses["setpoint_freshness"] = _clause(
                "EXPOSURE",
                "stale setpoint use is observed but this revision has no enforced freshness policy",
                evidence={"stale_consumption_ms": stale_consumption_ms},
            )
            categories.append("UNBOUNDED_FRESHNESS_POLICY_GAP")
        else:
            clauses["setpoint_freshness"] = _clause(
                "UNKNOWN", "no explicit freshness policy exists for a PASS adjudication"
            )

    if last_consumption is None or px4_receive is None:
        clauses["controller_continuation"] = _clause(
            "UNKNOWN", "controller consumption lineage is incomplete"
        )
    elif not target_complete:
        clauses["controller_continuation"] = _clause(
            "UNKNOWN", "pre-revocation target window is incomplete"
        )
    else:
        controller_continuation_ms = _duration_ms(last_consumption, px4_receive)
        assert controller_continuation_ms is not None
        if clauses["setpoint_freshness"]["status"] == "VIOLATION":
            clauses["controller_continuation"] = _clause(
                "VIOLATION",
                "controller continued using the command beyond its freshness deadline",
                evidence={"continuation_ms": controller_continuation_ms},
            )
        elif freshness_kind == "EXPLICIT" and timeout_ms is not None:
            clauses["controller_continuation"] = _clause(
                "PASS",
                "controller continuation remained within the explicit freshness policy",
                evidence={"continuation_ms": controller_continuation_ms},
            )
        elif controller_continuation_ms > measurement_tolerance_ms:
            clauses["controller_continuation"] = _clause(
                "EXPOSURE",
                "controller continued using the last received external setpoint",
                evidence={"continuation_ms": controller_continuation_ms},
            )
        else:
            clauses["controller_continuation"] = _clause(
                "PASS", evidence={"continuation_ms": controller_continuation_ms}
            )

    if px4_receive is None or last_allocator is None or last_writer is None:
        clauses["allocator_writer_continuation"] = _clause(
            "UNKNOWN", "allocator or final-writer lineage evidence is missing"
        )
    elif not target_complete:
        clauses["allocator_writer_continuation"] = _clause(
            "UNKNOWN", "pre-revocation target window is incomplete"
        )
    else:
        allocator_continuation_ms = _duration_ms(last_allocator, px4_receive)
        writer_continuation_ms = _duration_ms(last_writer, px4_receive)
        assert allocator_continuation_ms is not None and writer_continuation_ms is not None
        effect_deadline = (
            fallback_installed + route_grace_ms * 1000.0
            if fallback_installed is not None
            else None
        )
        if effect_deadline is not None and max(last_allocator, last_writer) > effect_deadline:
            clauses["allocator_writer_continuation"] = _clause(
                "VIOLATION",
                "external-route influence continued after fallback installation and route grace",
                evidence={
                    "allocator_continuation_ms": allocator_continuation_ms,
                    "writer_continuation_ms": writer_continuation_ms,
                    "post_fallback_grace_ms": route_grace_ms,
                },
            )
            categories.append("POST_FALLBACK_EXTERNAL_EFFECT")
        elif clauses["setpoint_freshness"]["status"] == "VIOLATION":
            clauses["allocator_writer_continuation"] = _clause(
                "VIOLATION",
                "policy-expired command propagated to allocator or final writer",
                evidence={
                    "allocator_continuation_ms": allocator_continuation_ms,
                    "writer_continuation_ms": writer_continuation_ms,
                },
            )
        elif freshness_kind == "EXPLICIT" and timeout_ms is not None:
            clauses["allocator_writer_continuation"] = _clause(
                "PASS",
                "downstream continuation remained within the explicit freshness policy",
                evidence={
                    "allocator_continuation_ms": allocator_continuation_ms,
                    "writer_continuation_ms": writer_continuation_ms,
                },
            )
        elif max(allocator_continuation_ms, writer_continuation_ms) > measurement_tolerance_ms:
            clauses["allocator_writer_continuation"] = _clause(
                "EXPOSURE",
                "the retained command continued influencing allocator and actuator output",
                evidence={
                    "allocator_continuation_ms": allocator_continuation_ms,
                    "writer_continuation_ms": writer_continuation_ms,
                },
            )
        else:
            clauses["allocator_writer_continuation"] = _clause(
                "PASS",
                evidence={
                    "allocator_continuation_ms": allocator_continuation_ms,
                    "writer_continuation_ms": writer_continuation_ms,
                },
            )

    health_deadline_ms = _number(policy.get("health_loss_deadline_ms"))
    installation_deadline_ms = _number(policy.get("fallback_installation_after_health_ms"))
    expects_health_alive = fault_type == "SETPOINT_ONLY_STALL"
    health_alive = observation.get("health_alive_through_target_window")
    if expects_health_alive:
        if not target_complete or health_alive is not True:
            clauses["fallback_detection"] = _clause(
                "UNKNOWN", "continuous health-reply evidence or target window is incomplete"
            )
        elif health_loss is not None or fallback_declared is not None:
            clauses["fallback_detection"] = _clause(
                "VIOLATION", "health loss/fallback was declared while health replies remained alive"
            )
            categories.append("FALSE_HEALTH_LOSS_DETECTION")
        else:
            clauses["fallback_detection"] = _clause(
                "PASS", "no health-loss detection was expected while replies remained alive"
            )
    elif fault is None or health_loss is None or health_deadline_ms is None:
        clauses["fallback_detection"] = _clause(
            "UNKNOWN", "health-loss timestamp, fault timestamp, or registered deadline is missing"
        )
    else:
        health_latency_ms = _duration_ms(health_loss, fault)
        assert health_latency_ms is not None
        if health_latency_ms > health_deadline_ms:
            clauses["fallback_detection"] = _clause(
                "VIOLATION",
                "health-loss detection exceeded the preregistered health deadline",
                evidence={"latency_ms": health_latency_ms, "deadline_ms": health_deadline_ms},
            )
            categories.append("HEALTH_LOSS_DEADLINE_EXCEEDED")
        else:
            clauses["fallback_detection"] = _clause(
                "PASS", evidence={"latency_ms": health_latency_ms, "deadline_ms": health_deadline_ms}
            )

    if expects_health_alive:
        if not target_complete:
            clauses["fallback_installation"] = _clause(
                "UNKNOWN", "target window is incomplete"
            )
        elif fallback_installed is None and observation.get("external_route_retained_at_window_end") is True:
            clauses["fallback_installation"] = _clause(
                "PASS", "source semantics predict no fallback while health remains alive"
            )
        elif fallback_installed is None:
            clauses["fallback_installation"] = _clause(
                "UNKNOWN", "route-retention evidence is missing"
            )
        else:
            clauses["fallback_installation"] = _clause(
                "VIOLATION", "unexpected fallback was installed during a health-alive stall"
            )
            categories.append("UNEXPECTED_FALLBACK")
    elif (
        health_loss is None
        or fallback_declared is None
        or fallback_installed is None
        or installation_deadline_ms is None
        or not _window_complete(observation, "fallback")
    ):
        clauses["fallback_installation"] = _clause(
            "UNKNOWN", "fallback declaration/installation evidence or window is incomplete"
        )
    else:
        declaration_latency_ms = _duration_ms(fallback_declared, health_loss)
        installation_latency_ms = _duration_ms(fallback_installed, health_loss)
        assert declaration_latency_ms is not None and installation_latency_ms is not None
        if installation_latency_ms > installation_deadline_ms:
            clauses["fallback_installation"] = _clause(
                "VIOLATION",
                "fallback installation exceeded its post-detection deadline",
                evidence={
                    "declaration_latency_ms": declaration_latency_ms,
                    "installation_latency_ms": installation_latency_ms,
                    "deadline_ms": installation_deadline_ms,
                },
            )
            categories.append("FALLBACK_INSTALLATION_DEADLINE_EXCEEDED")
        else:
            clauses["fallback_installation"] = _clause(
                "PASS",
                evidence={
                    "declaration_latency_ms": declaration_latency_ms,
                    "installation_latency_ms": installation_latency_ms,
                    "deadline_ms": installation_deadline_ms,
                },
            )

    metrics = observation.get("physical_metrics")
    thresholds = profile.get("physical_thresholds")
    if not _window_complete(observation, "pre_fault_stable"):
        clauses["physical_consequence"] = _clause(
            "UNKNOWN", "pre-fault physical baseline window is incomplete"
        )
    elif not isinstance(metrics, dict) or not isinstance(thresholds, dict):
        clauses["physical_consequence"] = _clause(
            "UNKNOWN", "physical metrics or preregistered thresholds are missing"
        )
    else:
        missing_metrics = [name for name in thresholds if _number(metrics.get(name)) is None]
        if missing_metrics:
            clauses["physical_consequence"] = _clause(
                "UNKNOWN", "required physical metrics are missing", evidence={"missing": missing_metrics}
            )
        else:
            exceeded = {
                name: {"observed": _number(metrics[name]), "threshold": _number(limit)}
                for name, limit in thresholds.items()
                if _number(limit) is not None and _number(metrics[name]) is not None
                and float(metrics[name]) > float(limit)
            }
            if exceeded:
                clauses["physical_consequence"] = _clause(
                    "EXPOSURE",
                    "one or more preregistered physical exposure thresholds were exceeded",
                    evidence={"exceeded": exceeded},
                )
                categories.append("PHYSICAL_EXPOSURE_THRESHOLD_EXCEEDED")
            else:
                clauses["physical_consequence"] = _clause(
                    "PASS", evidence={"metrics": metrics, "thresholds": thresholds}
                )

    recovery_deadline_ms = _number(policy.get("physical_recovery_after_fallback_ms"))
    if expects_health_alive and fallback_installed is None:
        clauses["recovery"] = _clause(
            "NOT_APPLICABLE", "no fallback/recovery is expected in the bounded health-alive window"
        )
    elif fallback_installed is None or recovery_time is None or recovery_deadline_ms is None:
        clauses["recovery"] = _clause(
            "UNKNOWN", "fallback or physical recovery timestamp/deadline is missing"
        )
    else:
        recovery_duration_ms = _duration_ms(recovery_time, fallback_installed)
        assert recovery_duration_ms is not None
        if recovery_duration_ms > recovery_deadline_ms:
            clauses["recovery"] = _clause(
                "VIOLATION",
                "physical recovery exceeded the preregistered deadline",
                evidence={"duration_ms": recovery_duration_ms, "deadline_ms": recovery_deadline_ms},
            )
            categories.append("RECOVERY_DEADLINE_EXCEEDED")
        else:
            clauses["recovery"] = _clause(
                "PASS",
                evidence={"duration_ms": recovery_duration_ms, "deadline_ms": recovery_deadline_ms},
            )

    derived = {
        "fault_to_last_setpoint_publish_ms": _duration_ms(producer_last, fault),
        "fault_to_last_px4_receive_ms": _duration_ms(px4_receive, fault),
        "fault_to_last_controller_consumption_ms": _duration_ms(last_consumption, fault),
        "fault_to_last_external_allocator_input_ms": _duration_ms(last_allocator, fault),
        "fault_to_last_external_writer_output_ms": _duration_ms(last_writer, fault),
        "fault_to_health_loss_detection_ms": _duration_ms(health_loss, fault),
        "fault_to_fallback_declaration_ms": _duration_ms(fallback_declared, fault),
        "fault_to_fallback_installation_ms": _duration_ms(fallback_installed, fault),
        "maximum_setpoint_age_ms": max(
            value for value in (stale_consumption_ms, _duration_ms(last_allocator, px4_receive), _duration_ms(last_writer, px4_receive))
            if value is not None
        ) if any(value is not None for value in (stale_consumption_ms, _duration_ms(last_allocator, px4_receive), _duration_ms(last_writer, px4_receive))) else None,
        "recovery_duration_ms": _duration_ms(recovery_time, fallback_installed),
    }
    return _result(profile, observation, clauses, categories, derived, True, None)


def _result(
    profile: dict[str, Any],
    observation: dict[str, Any],
    clauses: dict[str, dict[str, object]],
    categories: list[str],
    derived: dict[str, float | None],
    eligible: bool,
    exclusion_reason: str | None,
) -> dict[str, Any]:
    statuses = [str(clause["status"]) for clause in clauses.values()]
    if "VIOLATION" in statuses:
        overall = "VIOLATION"
    elif "UNKNOWN" in statuses:
        overall = "UNKNOWN"
    elif "EXPOSURE" in statuses:
        overall = "EXPOSURE"
    elif statuses and all(status == "NOT_APPLICABLE" for status in statuses):
        overall = "NOT_APPLICABLE"
    else:
        overall = "PASS"
    result = {
        "schema_version": "1.0",
        "oracle_name": "Pre-Revocation Freshness Oracle",
        "oracle_version": "0.1",
        "run_id": str(observation.get("run_id", "unknown")),
        "profile_id": str(profile.get("profile_id", "unknown")),
        "setpoint_type": str(observation.get("setpoint_type", "UNKNOWN")),
        "fault_type": str(observation.get("fault_type", "UNKNOWN")),
        "status": overall,
        "eligible_for_accepted_run": eligible and overall != "UNKNOWN",
        "exclusion_reason": exclusion_reason,
        "clauses": clauses,
        "categories": sorted(set(categories)),
        "derived_metrics": derived,
        "inputs": observation.get("inputs", {}),
    }
    Draft202012Validator(
        json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(result)
    return result


def _load_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(_load_mapping(args.profile), _load_mapping(args.observation))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
