from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "design" / "OBSERVABILITY_MATRIX.tsv"
FIELDS = {
    "declared_mode", "registration_state", "authority_source", "producer_identity",
    "setpoint_level", "setpoint_topic", "message_freshness", "enabled_modules",
    "bypassed_modules", "allocator_input", "actuator_writer", "actuator_output",
    "failsafe_state", "fallback_target",
}
STATUSES = {"DIRECT", "DERIVED", "INSTRUMENTATION_REQUIRED", "UNOBSERVABLE"}


def read_rows() -> list[dict[str, str]]:
    with MATRIX.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_all_route_fields_have_evidence_contracts() -> None:
    rows = read_rows()
    assert {row["route_field"] for row in rows} == FIELDS
    assert len(rows) == 14
    for row in rows:
        assert row["status"] in STATUSES
        for column in ("source_path", "symbol", "topic_or_event", "collection_method", "timestamp_source", "confidence", "limitations"):
            assert row[column].strip(), (row["route_field"], column)


def test_instrumented_fields_name_patch_and_collector() -> None:
    rows = read_rows()
    for row in rows:
        if row["status"] == "INSTRUMENTATION_REQUIRED":
            assert row["requires_px4_patch"] == "yes"
            assert "route_observability" in (row["topic_or_event"] + row["collection_method"])
