"""Deterministic, bounded Fuzzer v0 mutation operators."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import random
from typing import Any, Callable

from .case_model import SemanticCaseError, case_digest, validate_case


class MutationRejected(ValueError):
    """A selected mutation cannot produce a valid case from this parent."""


@dataclass(frozen=True)
class MutationResult:
    case: dict[str, Any]
    operator: str
    parameters: dict[str, Any]


def _finish(case: dict[str, Any], operator: str, parameters: dict[str, Any]) -> MutationResult:
    digest = case_digest(case)
    case["case_id"] = f"fuzz-{digest[:16]}"
    try:
        validate_case(case)
    except SemanticCaseError as exc:
        raise MutationRejected(str(exc)) from exc
    return MutationResult(case, operator, parameters)


def temporal_mutation(parent: dict[str, Any], rng: random.Random) -> MutationResult:
    case = copy.deepcopy(parent)
    index = rng.randrange(len(case["transition_events"]))
    delta = rng.choice((-0.5, -0.25, 0.25, 0.5))
    event = case["transition_events"][index]
    event["offset_s"] = min(12.0, max(0.0, round(float(event["offset_s"]) + delta, 3)))
    case["transition_events"].sort(key=lambda item: float(item["offset_s"]))
    case["timing"]["fault_offset_s"] = min(
        12.0, max(0.0, round(float(case["timing"]["fault_offset_s"]) + delta, 3))
    )
    return _finish(case, "temporal", {"event_id": event["event_id"], "delta_s": delta})


def state_conditioned_mutation(parent: dict[str, Any], rng: random.Random) -> MutationResult:
    case = copy.deepcopy(parent)
    index = rng.randrange(len(case["transition_events"]))
    context = case["behavior_context"]
    quantity, maximum = {
        "hover": ("speed_m_s", 0.5),
        "straight": ("speed_m_s", 2.0),
        "turn": ("turn_rate_rad_s", 0.35),
        "descent": ("descent_rate_m_s", 0.5),
    }[context]
    value = round(rng.uniform(maximum * 0.25, maximum * 0.75), 3)
    case["transition_events"][index]["condition"] = {
        "quantity": quantity,
        "operator": "ge",
        "value": value,
        "timeout_s": 8.0,
    }
    return _finish(
        case,
        "state_conditioned",
        {"event_id": case["transition_events"][index]["event_id"], "quantity": quantity, "value": value},
    )


def sequence_mutation(parent: dict[str, Any], rng: random.Random) -> MutationResult:
    case = copy.deepcopy(parent)
    events = case["transition_events"]
    choices = ["repeat", "insert_fallback"]
    operation = rng.choice(choices)
    if operation == "repeat" and len(events) < 12:
        source = copy.deepcopy(rng.choice(events))
        source["event_id"] = f"repeat-{len(events)}"
        source["offset_s"] = min(
            12.0,
            round(float(events[-1]["offset_s"]) + float(case["timing"]["repeated_transition_interval_s"]), 3),
        )
        if source["kind"] in {"process_sigterm", "process_sigkill", "process_pause"}:
            source["kind"] = "fallback"
            source.pop("duration_s", None)
        events.append(source)
    elif operation == "insert_fallback" and len(events) < 12:
        events.append(
            {
                "event_id": f"fallback-{len(events)}",
                "kind": "fallback",
                "offset_s": min(12.0, round(float(events[-1]["offset_s"]) + 0.5, 3)),
            }
        )
    else:
        raise MutationRejected("sequence is already at the v0 event limit")
    events.sort(key=lambda item: float(item["offset_s"]))
    return _finish(case, "sequence", {"operation": operation})


def channel_mutation(parent: dict[str, Any], rng: random.Random) -> MutationResult:
    case = copy.deepcopy(parent)
    state = copy.deepcopy(case["channel_states"][-1])
    channel = rng.choice(("liveness", "setpoint"))
    state[channel] = "off" if state[channel] == "on" else "on"
    state["offset_s"] = min(12.0, round(float(state["offset_s"]) + 0.5, 3))
    case["channel_states"].append(state)
    event_kind = f"heartbeat_{state[channel]}" if channel == "liveness" else f"setpoint_{state[channel]}"
    case["transition_events"].append(
        {
            "event_id": f"channel-{len(case['transition_events'])}",
            "kind": event_kind,
            "offset_s": state["offset_s"],
        }
    )
    case["transition_events"].sort(key=lambda item: float(item["offset_s"]))
    return _finish(case, "channel", {"channel": channel, "state": state[channel]})


def context_mutation(parent: dict[str, Any], rng: random.Random) -> MutationResult:
    case = copy.deepcopy(parent)
    contexts = [name for name in ("hover", "straight", "turn", "descent") if name != case["behavior_context"]]
    context = rng.choice(contexts)
    case["behavior_context"] = context
    constraints = case["initial_state_constraints"]
    if context == "straight":
        constraints["maximum_speed_m_s"] = round(rng.uniform(0.5, 2.0), 3)
    elif context == "turn":
        constraints["maximum_turn_rate_rad_s"] = round(rng.uniform(0.1, 0.35), 3)
    elif context == "descent":
        constraints["maximum_descent_rate_m_s"] = round(rng.uniform(0.1, 0.5), 3)
    return _finish(case, "context", {"context": context})


OPERATORS: dict[str, Callable[[dict[str, Any], random.Random], MutationResult]] = {
    "temporal": temporal_mutation,
    "state_conditioned": state_conditioned_mutation,
    "sequence": sequence_mutation,
    "channel": channel_mutation,
    "context": context_mutation,
}


def mutate(
    parent: dict[str, Any], *, rng_seed: int, operator: str | None = None
) -> MutationResult:
    rng = random.Random(rng_seed)
    names = [operator] if operator else list(OPERATORS)
    if any(name not in OPERATORS for name in names):
        raise ValueError(f"unknown mutation operator: {operator}")
    rng.shuffle(names)
    failures: list[str] = []
    for name in names:
        try:
            return OPERATORS[name](parent, rng)
        except MutationRejected as exc:
            failures.append(f"{name}: {exc}")
    raise MutationRejected("; ".join(failures))
