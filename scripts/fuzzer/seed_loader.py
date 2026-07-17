"""Load and validate the versioned Fuzzer v0 seed corpus."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .case_model import load_case
from .case_model import validate_case


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_ROOT = ROOT / "experiments/fuzzer_v0/seeds"
DEFAULT_MANIFEST = ROOT / "experiments/fuzzer_v0/seed_manifest.yaml"


def _expanded_seed(entry: dict[str, Any]) -> dict[str, Any]:
    mechanism = str(entry["mechanism"])
    transition = str(entry["transition_class"])
    external_route = (
        "dynamic_external_mode" if mechanism == "dynamic_external_mode" else "legacy_offboard"
    )
    source_route = "internal_takeoff" if transition == "T1" else external_route
    target_route = external_route if transition == "T1" else "internal_hold"
    kind = {
        "T1": "activate",
        "T2": "complete",
        "T4": "process_sigterm",
        "T5": "process_sigkill",
        "T6": "process_pause",
        "T7": "setpoint_off",
        "T8": "heartbeat_off",
    }[transition]
    events: list[dict[str, Any]] = []
    if transition == "T1":
        events.append({"event_id": "admit", "kind": "admit", "offset_s": 0.0})
    event: dict[str, Any] = {"event_id": "primary", "kind": kind, "offset_s": 2.0}
    if transition == "T6":
        event["duration_s"] = 1.0
    events.append(event)
    if transition not in {"T1", "T2"}:
        events.append({"event_id": "fallback", "kind": "fallback", "offset_s": 3.5})
    channels = [
        {
            "offset_s": 0.0,
            "liveness": "on",
            "setpoint": "on",
            "registration": "registered" if mechanism == "dynamic_external_mode" else "not_applicable",
            "process_state": "running",
        }
    ]
    if transition == "T7":
        channels.append({**channels[0], "offset_s": 2.0, "setpoint": "off"})
    elif transition == "T8":
        channels.append({**channels[0], "offset_s": 2.0, "liveness": "off"})
    faults = []
    if transition in {"T4", "T5", "T6"}:
        faults.append(
            {
                "fault_id": "producer-fault",
                "kind": {"T4": "sigterm", "T5": "sigkill", "T6": "pause"}[transition],
                "target_session": "case_producer",
                "event_id": "primary",
            }
        )
    context = str(entry["context"])
    profile = str(entry.get("profile", "canonical"))
    validation_only = bool(entry.get("validation_only", False))
    case = {
        "schema_version": "1.0",
        "case_id": str(entry["case_id"]),
        "seed_id": str(entry["seed_id"]),
        "route_family": "family_a_external_autonomy",
        "source_route": source_route,
        "target_route": target_route,
        "fallback_route": "internal_hold",
        "behavior_context": context,
        "initial_state_constraints": {
            "armed": True,
            "minimum_altitude_m": 2.0,
            "maximum_speed_m_s": 0.5 if context == "hover" else 1.0,
            "maximum_descent_rate_m_s": 0.3,
            "maximum_turn_rate_rad_s": 0.2,
        },
        "transition_events": events,
        "channel_states": channels,
        "faults": faults,
        "timing": {
            "fault_offset_s": 2.0,
            "heartbeat_setpoint_skew_s": 0.0,
            "repeated_transition_interval_s": 2.0,
            "maximum_duration_s": 150.0,
        },
        "repetition": {"count": 1, "simulation_seed": int(entry["simulation_seed"])},
        "environment": {
            "profile": profile,
            "vehicle": "x500",
            "world": "default",
            "sitl_only": True,
            "wind_m_s": 0.0,
            "observation_profile": "TRANSITION",
        },
        "provenance": {
            "source": str(entry["source"]),
            "source_case": str(entry["source_case"]),
            "validation_only": validation_only,
        },
    }
    return validate_case(case)


def load_seeds(
    root: Path = DEFAULT_SEED_ROOT,
    *,
    include_validation_only: bool = False,
    discovery_profile: bool = False,
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    seen: set[str] = set()
    if root == DEFAULT_SEED_ROOT and DEFAULT_MANIFEST.exists():
        manifest = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        for entry in manifest["seeds"]:
            case = _expanded_seed(entry)
            validation_only = bool(case["provenance"]["validation_only"])
            if validation_only and not include_validation_only:
                continue
            if discovery_profile:
                validate_case(case, discovery_profile=True)
            if case["case_id"] in seen:
                raise ValueError(f"duplicate seed case_id: {case['case_id']}")
            seen.add(case["case_id"])
            seeds.append(case)
    for path in sorted(root.glob("*.json")):
        case = load_case(path, discovery_profile=discovery_profile)
        validation_only = bool(case.get("provenance", {}).get("validation_only", False))
        if validation_only and not include_validation_only:
            continue
        if case["case_id"] in seen:
            raise ValueError(f"duplicate seed case_id: {case['case_id']}")
        seen.add(case["case_id"])
        seeds.append(case)
    if not seeds:
        raise ValueError(f"no usable fuzz seeds found under {root}")
    return seeds
