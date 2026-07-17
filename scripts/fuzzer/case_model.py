"""Fuzzer v0 case schema, canonicalization, and semantic grammar checks."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[2]
CASE_SCHEMA_PATH = ROOT / "data/schemas/fuzz_case.schema.json"
RESULT_SCHEMA_PATH = ROOT / "data/schemas/fuzz_result.schema.json"
CASE_SCHEMA = json.loads(CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
RESULT_SCHEMA = json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
CASE_VALIDATOR = Draft202012Validator(CASE_SCHEMA)
RESULT_VALIDATOR = Draft202012Validator(RESULT_SCHEMA)

TERMINAL_PROCESS_EVENTS = {"process_sigterm", "process_sigkill"}
PROCESS_FAULTS = TERMINAL_PROCESS_EVENTS | {"process_pause"}
EXTERNAL_ROUTES = {"legacy_offboard", "dynamic_external_mode"}


class SemanticCaseError(ValueError):
    """A schema-valid case violates the frozen transition grammar."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _semantic_payload(case: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(case)
    payload.pop("case_id", None)
    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("mutation", None)
    return payload


def case_digest(case: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_semantic_payload(case)).encode()).hexdigest()


def duplicate_fingerprint(case: dict[str, Any]) -> str:
    timing = case["timing"]
    fingerprint = {
        "route_family": case["route_family"],
        "routes": [case["source_route"], case["target_route"], case["fallback_route"]],
        "context": case["behavior_context"],
        "events": [event["kind"] for event in case["transition_events"]],
        "channels": [
            [state[key] for key in ("liveness", "setpoint", "registration", "process_state")]
            for state in case["channel_states"]
        ],
        "faults": [[fault["kind"], fault["target_session"]] for fault in case["faults"]],
        "timing_bins": [
            round(float(timing["fault_offset_s"]) * 4) / 4,
            round(float(timing["heartbeat_setpoint_skew_s"]) * 4) / 4,
            round(float(timing["repeated_transition_interval_s"]) * 2) / 2,
        ],
    }
    return hashlib.sha256(canonical_json(fingerprint).encode()).hexdigest()


def _event_error(message: str) -> None:
    raise SemanticCaseError(message)


def validate_semantics(case: dict[str, Any], *, discovery_profile: bool = False) -> None:
    events = case["transition_events"]
    offsets = [float(event["offset_s"]) for event in events]
    if offsets != sorted(offsets):
        _event_error("transition event offsets must be monotonically nondecreasing")
    event_ids = [str(event["event_id"]) for event in events]
    if len(event_ids) != len(set(event_ids)):
        _event_error("transition event IDs must be unique")
    by_kind: dict[str, list[int]] = {}
    for index, event in enumerate(events):
        by_kind.setdefault(str(event["kind"]), []).append(index)

    if "activate" in by_kind and "admit" in by_kind:
        if min(by_kind["activate"]) < min(by_kind["admit"]):
            _event_error("activate cannot precede admit")
    if "unregister" in by_kind and case["source_route"] != "dynamic_external_mode":
        _event_error("unregister requires dynamic_external_mode lifecycle")
    if sum(len(by_kind.get(kind, [])) for kind in PROCESS_FAULTS) > 1:
        _event_error("v0 permits at most one process fault")
    for kind in TERMINAL_PROCESS_EVENTS:
        for terminal_index in by_kind.get(kind, []):
            disallowed = {
                str(event["kind"])
                for event in events[terminal_index + 1 :]
                if event["kind"] not in {"fallback", "reentry"}
            }
            if disallowed:
                _event_error("only fallback/reentry observation may follow process termination")
    for index in by_kind.get("process_pause", []):
        if "duration_s" not in events[index]:
            _event_error("process_pause requires a bounded duration")
    for off, on in (("heartbeat_off", "heartbeat_on"), ("setpoint_off", "setpoint_on")):
        if on in by_kind and (off not in by_kind or min(by_kind[on]) < min(by_kind[off])):
            _event_error(f"{on} requires a preceding {off}")
    if "reentry" in by_kind and not any(
        kind in by_kind
        for kind in {"complete", "cancel", "release", "unregister", "fallback", *PROCESS_FAULTS}
    ):
        _event_error("reentry requires a prior exit or fallback")

    fault_events = {fault["event_id"] for fault in case["faults"]}
    if not fault_events <= set(event_ids):
        _event_error("every fault must reference a transition event")
    if any(float(state["offset_s"]) > float(case["timing"]["maximum_duration_s"])
           for state in case["channel_states"]):
        _event_error("channel state occurs after maximum duration")
    if case["source_route"] not in EXTERNAL_ROUTES and not any(
        event["kind"] in {"admit", "activate"} for event in events
    ):
        _event_error("an internal source requires an admission/activation transition")

    profile = case["environment"]["profile"]
    validation_only = bool(case.get("provenance", {}).get("validation_only", False))
    if profile == "oracle_validation_mutant" and not validation_only:
        _event_error("mutant profiles must be explicitly validation-only")
    if discovery_profile and (profile != "canonical" or validation_only):
        _event_error("discovery execution requires the canonical non-mutant profile")


def validate_case(case: dict[str, Any], *, discovery_profile: bool = False) -> dict[str, Any]:
    CASE_VALIDATOR.validate(case)
    validate_semantics(case, discovery_profile=discovery_profile)
    return case


def load_case(path: Path, *, discovery_profile: bool = False) -> dict[str, Any]:
    case = json.loads(path.read_text(encoding="utf-8"))
    return validate_case(case, discovery_profile=discovery_profile)


def write_case(case: dict[str, Any], path: Path) -> None:
    validate_case(case)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    RESULT_VALIDATOR.validate(result)
    return result


__all__ = [
    "SemanticCaseError",
    "ValidationError",
    "case_digest",
    "canonical_json",
    "duplicate_fingerprint",
    "load_case",
    "validate_case",
    "validate_result",
    "write_case",
]
