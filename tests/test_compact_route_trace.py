from __future__ import annotations

import json

from scripts.tracing.compact_route_trace import compact


def test_compaction_preserves_lifecycle_and_epoch_boundaries(tmp_path) -> None:
    source = tmp_path / "full.jsonl"
    output = tmp_path / "compact.jsonl"
    events = [
        {"event_type": "route_epoch_changed", "route_epoch_id": 1},
        *(
            {"event_type": "actuator_output_published", "route_epoch_id": 1, "sequence": i}
            for i in range(11)
        ),
        {"event_type": "unregister_request_processed", "route_epoch_id": 1},
    ]
    source.write_text("".join(json.dumps(event) + "\n" for event in events))
    report = compact(source, output, stride=5)
    retained = [json.loads(line) for line in output.read_text().splitlines()]
    assert [event["sequence"] for event in retained if "sequence" in event] == [0, 5, 10]
    assert retained[0]["event_type"] == "route_epoch_changed"
    assert retained[-1]["event_type"] == "unregister_request_processed"
    assert report["full_event_count"] == 13
    assert report["compact_event_count"] == 5
