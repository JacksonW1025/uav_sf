from __future__ import annotations

import json
from pathlib import Path

from scripts.analysis.summarize_registration_lifecycle import summarize


def _event(event_type: str, result: str = "SUCCESS", executor_id: int = -1) -> dict[str, object]:
    return {
        "event_type": event_type,
        "registration_state": {
            "registered": event_type == "register_ext_component_reply",
            "mode_id": 23,
            "mode_executor_id": executor_id,
            "arming_check_id": 0,
            "processing_result": result,
        },
    }


def test_two_clean_registration_cycles_pass(tmp_path: Path) -> None:
    events = []
    for _ in range(2):
        events.extend(
            (
                _event("register_ext_component_reply"),
                _event("arming_check_slot_removed"),
                _event("external_mode_slot_removed"),
                _event("unregister_request_processed"),
            )
        )
    trace = tmp_path / "trace.jsonl"
    trace.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    logs = []
    for index in range(2):
        path = tmp_path / f"mode{index}.log"
        path.write_text(
            '[INFO] {"event_type":"external_mode_registered",'
            f'"registration_instance_id":{100 + index},"mode_id":23}}\n',
            encoding="utf-8",
        )
        logs.append(path)
    result = summarize(trace, logs, True, True)
    assert result["status"] == "PASS"
    assert result["checks"]["executor_slot_status_explicit"] is True


def test_missing_slot_removal_fails(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "".join(json.dumps(_event("register_ext_component_reply")) + "\n" for _ in range(2)),
        encoding="utf-8",
    )
    log = tmp_path / "mode.log"
    log.write_text(
        '[INFO] {"event_type":"external_mode_registered",'
        '"registration_instance_id":100,"mode_id":23}\n',
        encoding="utf-8",
    )
    assert summarize(trace, [log], True, True)["status"] == "FAIL"
