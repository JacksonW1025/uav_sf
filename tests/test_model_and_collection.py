from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.adapters.family_a import FamilyAAdapter
from scripts.collectors.trace_collector import CollectorError, TraceCollector, collect_stream
from scripts.model.runtime_route import RuntimeRouteInstance, RouteModelError, read_trace
from tests.helpers import identity


class ModelAndCollectionTests(unittest.TestCase):
    def test_runtime_route_identity_is_complete(self) -> None:
        value = RuntimeRouteInstance(**identity("legacy_offboard", "source"))
        self.assertEqual(value.route_epoch, "epoch-source")
        with self.assertRaises(RouteModelError):
            RuntimeRouteInstance.from_event({"route": "legacy_offboard"})

    def test_adapter_normalizes_aliases(self) -> None:
        raw = {
            "event": "command_consumed",
            "analysis_timestamp_ns": 20,
            "clock_domain": "px4_boot",
            "command_timestamp_ns": 10,
            **identity("legacy_offboard", "source"),
        }
        adapted = FamilyAAdapter("legacy_offboard").adapt(raw, run_id="run-a")
        self.assertEqual(adapted["kind"], "command_consumed")
        self.assertEqual(adapted["command_subject_ns"], 10)

    def test_collector_hash_chain_round_trip_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            with TraceCollector(path, "run-a") as collector:
                collector.append(
                    {
                        "kind": "collection_started",
                        "timestamp_ns": 0,
                        "source_domain": "px4_boot",
                    }
                )
                collector.append(
                    {
                        "kind": "collection_stopped",
                        "timestamp_ns": 1,
                        "source_domain": "px4_boot",
                    }
                )
            self.assertEqual(len(read_trace(path)), 2)
            with self.assertRaises(CollectorError):
                TraceCollector(path, "run-a")

    def test_stream_collector_adds_bounds(self) -> None:
        source = io.StringIO(
            json.dumps(
                {
                    "event": "command_consumed",
                    "analysis_timestamp_ns": 10,
                    "command_timestamp_ns": 5,
                    **identity("legacy_offboard", "source"),
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            self.assertEqual(
                collect_stream(
                    source,
                    output=path,
                    run_id="run-a",
                    mechanism="legacy_offboard",
                ),
                0,
            )
            events = read_trace(path)
            self.assertEqual([event["kind"] for event in events], ["collection_started", "command_consumed", "collection_stopped"])


if __name__ == "__main__":
    unittest.main()
