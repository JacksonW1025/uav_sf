from __future__ import annotations

import hashlib
import json

from scripts.oracles.trace_mutator import load_trace, mutate


def _event(timestamp: int, event_type: str, mode: int, epoch: int) -> dict[str, object]:
    return {
        "schema_version": "1.2",
        "run_id": "base",
        "timestamp": timestamp,
        "timestamp_domain": "ulog_us",
        "event_type": event_type,
        "declared_mode": mode,
        "route_epoch_id": epoch,
        "actuator_writer": "control_allocator" if event_type == "actuator_output_published" else None,
        "observation": None,
        "evidence_source": "test",
    }


def test_mutation_preserves_base_and_inserts_old_epoch(tmp_path) -> None:
    base = tmp_path / "base.jsonl"
    output = tmp_path / "mutant.jsonl"
    events = [
        _event(0, "vehicle_status", 23, 1),
        _event(90, "px4_setpoint_consumed", 23, 1),
        _event(100, "vehicle_status", 5, 2),
        _event(110, "px4_setpoint_consumed", 5, 2),
    ]
    base.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    before = hashlib.sha256(base.read_bytes()).hexdigest()
    report = mutate(
        base,
        output,
        "revocation-mutant",
        [
            {
                "operator": "insert_old_epoch_event",
                "event_type": "px4_setpoint_consumed",
                "offset_us": 1,
            }
        ],
    )
    mutated = load_trace(output)
    assert hashlib.sha256(base.read_bytes()).hexdigest() == before
    assert report["base_sha256_before"] == report["base_sha256_after"]
    assert any(
        event["event_type"] == "px4_setpoint_consumed"
        and event["route_epoch_id"] == 1
        and event["timestamp"] == 101
        for event in mutated
    )
    assert all(event["run_id"] == "revocation-mutant" for event in mutated)
