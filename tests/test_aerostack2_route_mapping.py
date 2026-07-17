from __future__ import annotations

import json
from pathlib import Path

from scripts.tracing.route_trace_collector import RouteEventReducer, RouteTraceWriter
from scripts.workloads.aerostack2_trace_adapter import adapt


def _write_px4(path: Path, modes: list[int]) -> None:
    reducer = RouteEventReducer("source")
    RouteTraceWriter(path).write(
        reducer.reduce("vehicle_status", {"nav_state": mode}, 1_000_000 + index)
        for index, mode in enumerate(modes)
    )


def test_runtime_mapping_distinguishes_handoff_from_behavior_update(tmp_path: Path) -> None:
    as2 = tmp_path / "as2.jsonl"
    as2.write_text(
        json.dumps(
            {
                "timestamp_ns": 10,
                "event_type": "as2_action_completed",
                "node": "go_to_behavior",
                "action": "go_to",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    handoff_px4 = tmp_path / "handoff_px4.jsonl"
    _write_px4(handoff_px4, [4, 14])
    handoff = adapt(
        as2,
        handoff_px4,
        tmp_path / "handoff.jsonl",
        tmp_path / "handoff_summary.json",
        "a2-handoff",
    )
    assert handoff["classification"] == "TRUE_ROUTE_HANDOFF"
    assert handoff["true_handoffs"] == [[4, 14]]

    update_px4 = tmp_path / "update_px4.jsonl"
    _write_px4(update_px4, [14, 14])
    update = adapt(
        as2,
        update_px4,
        tmp_path / "update.jsonl",
        tmp_path / "update_summary.json",
        "a2-update",
    )
    assert update["classification"] == "NON_HANDOFF_TASK_TRANSITION"
    assert update["true_handoffs"] == []
