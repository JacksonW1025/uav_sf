from __future__ import annotations

from scripts.tracing.route_trace_collector import RouteEventReducer, ulog_row_order


def _observation(event_type: int, epoch: int, **fields: int) -> dict[str, int]:
    return {
        "event_type": event_type,
        "route_epoch_id": epoch,
        "sequence": 1,
        "source_id": 0,
        "topic_id": 0,
        "writer_id": 0,
        "instance": 0,
        "profile": 2,
        "expected_period_us": 0,
        "subject_timestamp": 100,
        **fields,
    }


def test_epoch_change_precedes_same_timestamp_data_event() -> None:
    rows = [
        (100.0, "route_observability", _observation(1, 0)),
        (
            100.0,
            "route_observability",
            _observation(4, 7, previous_nav_state=4, new_nav_state=14, change_source=1),
        ),
    ]
    reducer = RouteEventReducer("epoch-order")
    events = [
        reducer.reduce(source, payload, timestamp)
        for timestamp, source, payload in sorted(rows, key=ulog_row_order)
    ]
    assert events[0]["event_type"] == "route_epoch_changed"
    assert events[1]["event_type"] == "px4_setpoint_consumed"
    assert events[1]["route_epoch_id"] == 7


def test_epoch_identity_is_not_inferred_before_first_epoch_event() -> None:
    reducer = RouteEventReducer("epoch-null")
    event = reducer.reduce("route_observability", _observation(3, 0), 50.0)
    assert event["route_epoch_id"] is None
