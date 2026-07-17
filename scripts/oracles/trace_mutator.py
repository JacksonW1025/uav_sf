#!/usr/bin/env python3
"""Create deterministic, trace-only Route Oracle validation mutants."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.oracles.route_oracle_v0 import _mode_transition


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_trace(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_trace(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in sorted(events, key=lambda item: float(item["timestamp"]))
        ),
        encoding="utf-8",
    )


def _transition_context(events: list[dict[str, Any]]) -> tuple[dict[str, Any], Any, Any]:
    transition = _mode_transition(events)
    if transition is None:
        raise ValueError("mutation requires a declared route transition")
    exit_us = float(transition["timestamp_us"])
    target_epochs = [
        event.get("route_epoch_id")
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and float(event["timestamp"]) >= exit_us
        and event.get("declared_mode") == transition["target_mode"]
        and event.get("route_epoch_id") is not None
    ]
    target_epoch = target_epochs[0] if target_epochs else None
    return transition, transition.get("source_route_epoch_id"), target_epoch


def _renumber_writer_sequences(events: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    writer_events = sorted(
        (
            event
            for event in events
            if event.get("event_type") == "actuator_output_published"
            and event.get("timestamp_domain") == "ulog_us"
            and isinstance(event.get("observation"), dict)
        ),
        key=lambda item: float(item["timestamp"]),
    )
    for event in writer_events:
        writer = str(event.get("actuator_writer") or "unknown")
        sequence = counts.get(writer, 0)
        event["observation"]["sequence"] = sequence
        event["observation"]["subject_timestamp"] = float(event["timestamp"])
        counts[writer] = sequence + 1


def _matching_event(
    events: list[dict[str, Any]], event_type: str, mode: Any, before_us: float
) -> dict[str, Any]:
    matches = [
        event
        for event in events
        if event.get("event_type") == event_type
        and event.get("timestamp_domain") == "ulog_us"
        and event.get("declared_mode") == mode
        and float(event["timestamp"]) <= before_us
    ]
    if not matches:
        raise ValueError(f"base trace has no {event_type} template for mode {mode}")
    return max(matches, key=lambda item: float(item["timestamp"]))


def _insert_old_epoch_event(
    events: list[dict[str, Any]], event_type: str, offset_us: float
) -> None:
    transition, source_epoch, _ = _transition_context(events)
    template = copy.deepcopy(
        _matching_event(
            events,
            event_type,
            transition["source_mode"],
            float(transition["timestamp_us"]),
        )
    )
    template["timestamp"] = float(transition["timestamp_us"]) + offset_us
    template["route_epoch_id"] = source_epoch
    template["declared_mode"] = transition["source_mode"]
    template["evidence_source"] = "trace_mutator:post_revocation_old_epoch"
    events.append(template)


def _delete_target_evidence(events: list[dict[str, Any]], evidence: str) -> None:
    transition, _, _ = _transition_context(events)
    exit_us = float(transition["timestamp_us"])
    target_mode = transition["target_mode"]
    event_types = {
        "fresh_consumption": {"px4_setpoint_consumed"},
        "allocator_input": {"allocator_input_published"},
        "final_writer": {"actuator_output_published"},
    }
    if evidence in event_types:
        events[:] = [
            event
            for event in events
            if not (
                event.get("timestamp_domain") == "ulog_us"
                and float(event["timestamp"]) >= exit_us
                and event.get("declared_mode") == target_mode
                and event.get("event_type") in event_types[evidence]
            )
        ]
    elif evidence == "registration_or_activation":
        for event in events:
            if isinstance(event.get("registration_state"), dict):
                event["registration_state"] = None
    elif evidence == "enabled_modules":
        for event in events:
            if (
                event.get("timestamp_domain") == "ulog_us"
                and float(event["timestamp"]) >= exit_us
                and event.get("declared_mode") == target_mode
            ):
                event["enabled_modules"] = []
    elif evidence == "setpoint_configuration":
        for event in events:
            if (
                event.get("timestamp_domain") == "ulog_us"
                and float(event["timestamp"]) >= exit_us
                and event.get("declared_mode") == target_mode
            ):
                event["setpoint_level"] = "unknown"
    else:
        raise ValueError(f"unsupported target evidence: {evidence}")


def _delay_target_evidence(
    events: list[dict[str, Any]], event_types: set[str], delay_us: float
) -> None:
    transition, _, _ = _transition_context(events)
    exit_us = float(transition["timestamp_us"])
    for event in events:
        if (
            event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) >= exit_us
            and event.get("declared_mode") == transition["target_mode"]
            and event.get("event_type") in event_types
        ):
            event["timestamp"] = float(event["timestamp"]) + delay_us


def _add_competing_writer(events: list[dict[str, Any]], writer: str) -> None:
    transition, _, target_epoch = _transition_context(events)
    exit_us = float(transition["timestamp_us"])
    targets = [
        event
        for event in events
        if event.get("event_type") == "actuator_output_published"
        and event.get("timestamp_domain") == "ulog_us"
        and event.get("declared_mode") == transition["target_mode"]
        and float(event["timestamp"]) >= exit_us
    ]
    if not targets:
        raise ValueError("base trace has no target writer event")
    mutant = copy.deepcopy(min(targets, key=lambda item: float(item["timestamp"])))
    mutant["timestamp"] = float(mutant["timestamp"]) + 1.0
    mutant["actuator_writer"] = writer
    mutant["route_epoch_id"] = target_epoch
    mutant["evidence_source"] = "trace_mutator:competing_writer"
    if isinstance(mutant.get("observation"), dict):
        mutant["observation"]["writer_id"] = int(mutant["observation"]["writer_id"]) + 100
    events.append(mutant)


def _make_continuity_gap(events: list[dict[str, Any]], delay_us: float) -> None:
    transition, _, _ = _transition_context(events)
    exit_us = float(transition["timestamp_us"])
    for event in events:
        if (
            event.get("event_type") == "actuator_output_published"
            and event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) >= exit_us
        ):
            event["timestamp"] = float(event["timestamp"]) + delay_us


def _truncate_critical_window(events: list[dict[str, Any]], after_us: float) -> None:
    transition, _, _ = _transition_context(events)
    cutoff = float(transition["timestamp_us"]) + after_us
    events[:] = [event for event in events if float(event["timestamp"]) <= cutoff]


def _drop_writer_sequence(events: list[dict[str, Any]]) -> None:
    transition, _, _ = _transition_context(events)
    exit_us = float(transition["timestamp_us"])
    for event in events:
        if (
            event.get("event_type") == "actuator_output_published"
            and event.get("timestamp_domain") == "ulog_us"
            and float(event["timestamp"]) >= exit_us
        ):
            event["observation"] = None
            return
    raise ValueError("base trace has no target writer sequence to remove")


def _drop_source_route_epoch(events: list[dict[str, Any]]) -> None:
    transition, source_epoch, _ = _transition_context(events)
    for event in events:
        if (
            event.get("declared_mode") == transition["source_mode"]
            and event.get("route_epoch_id") == source_epoch
            and event.get("event_type")
            in {"px4_setpoint_consumed", "allocator_input_published", "actuator_output_published"}
        ):
            event["route_epoch_id"] = None


def _retain_no_transition(events: list[dict[str, Any]]) -> None:
    transition, _, _ = _transition_context(events)
    exit_us = float(transition["timestamp_us"])
    source_mode = transition["source_mode"]
    retained = [
        event
        for event in events
        if event.get("declared_mode") == source_mode
        and float(event["timestamp"]) <= exit_us
        and float(event["timestamp"]) >= exit_us - 500_000.0
    ]
    statuses = [event for event in retained if event.get("event_type") == "vehicle_status"]
    if not statuses:
        template = copy.deepcopy(
            _matching_event(events, "vehicle_status", source_mode, exit_us)
        )
        template["timestamp"] = max(0.0, exit_us - 1.0)
        retained.append(template)
    events[:] = retained


def _retain_transition(
    events: list[dict[str, Any]], source_mode: Any, target_mode: Any, padding_us: float
) -> None:
    statuses = sorted(
        (
            event
            for event in events
            if event.get("event_type") == "vehicle_status"
            and event.get("timestamp_domain") == "ulog_us"
        ),
        key=lambda item: float(item["timestamp"]),
    )
    transition_us: float | None = None
    previous_mode: Any = None
    initialized = False
    for event in statuses:
        mode = event.get("declared_mode")
        if initialized and previous_mode == source_mode and mode == target_mode:
            transition_us = float(event["timestamp"])
            break
        previous_mode = mode
        initialized = True
    if transition_us is None:
        raise ValueError(f"base trace has no {source_mode!r}->{target_mode!r} transition")
    lower = max(0.0, transition_us - padding_us)
    upper = transition_us + padding_us
    events[:] = [
        event
        for event in events
        if event.get("timestamp_domain") == "ulog_us"
        and lower <= float(event["timestamp"]) <= upper
    ]


def mutate(
    base_trace: Path,
    output_trace: Path,
    case_id: str,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    original_sha256 = _sha256(base_trace)
    events = copy.deepcopy(load_trace(base_trace))
    for event in events:
        event["run_id"] = case_id
    for operation in operations:
        name = operation["operator"]
        if name == "identity":
            continue
        if name == "insert_old_epoch_event":
            _insert_old_epoch_event(
                events,
                str(operation["event_type"]),
                float(operation.get("offset_us", 1_000.0)),
            )
        elif name == "delete_target_evidence":
            _delete_target_evidence(events, str(operation["evidence"]))
        elif name == "delay_target_evidence":
            _delay_target_evidence(
                events,
                set(operation["event_types"]),
                float(operation["delay_us"]),
            )
        elif name == "add_competing_writer":
            _add_competing_writer(events, str(operation["writer"]))
        elif name == "make_continuity_gap":
            _make_continuity_gap(events, float(operation["delay_us"]))
        elif name == "truncate_critical_window":
            _truncate_critical_window(events, float(operation.get("after_us", 5_000.0)))
        elif name == "drop_writer_sequence":
            _drop_writer_sequence(events)
        elif name == "drop_source_route_epoch":
            _drop_source_route_epoch(events)
        elif name == "retain_no_transition":
            _retain_no_transition(events)
        elif name == "retain_transition":
            _retain_transition(
                events,
                operation["source_mode"],
                operation["target_mode"],
                float(operation.get("padding_us", 500_000.0)),
            )
        else:
            raise ValueError(f"unsupported mutation operator: {name}")
        if name != "drop_writer_sequence":
            _renumber_writer_sequences(events)
    _write_trace(output_trace, events)
    if _sha256(base_trace) != original_sha256:
        raise RuntimeError("base trace changed during mutation")
    return {
        "case_id": case_id,
        "base_trace": str(base_trace),
        "base_sha256_before": original_sha256,
        "base_sha256_after": _sha256(base_trace),
        "mutated_trace": str(output_trace),
        "mutated_sha256": _sha256(output_trace),
        "event_count": len(events),
        "operators": [operation["operator"] for operation in operations],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--operations", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    operations = json.loads(args.operations.read_text(encoding="utf-8"))
    report = mutate(args.base_trace, args.output, args.case_id, operations)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
