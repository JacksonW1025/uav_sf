#!/usr/bin/env python3
"""Extract and fail-closed check RouteObservability evidence from a PX4 ULog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


REQUIRED_FIELDS = frozenset(
    {
        "timestamp",
        "subject_timestamp",
        "sequence",
        "expected_period_us",
        "route_epoch_id",
        "failed_check_mask",
        "component_hash",
        "event_type",
        "source_id",
        "topic_id",
        "writer_id",
        "profile",
        "instance",
        "previous_nav_state",
        "new_nav_state",
        "change_source",
        "registration_mode_id",
        "executor_in_charge",
        "arming_check_id",
        "result",
        "reason_code",
        "armed",
        "active_at_event",
        "fallback_nav_state",
    }
)


class ULogEvidenceError(ValueError):
    """The ULog cannot support an admissible normalized trace."""


def _scalar(value: Any) -> int | float | bool | str:
    converted = value.item() if hasattr(value, "item") else value
    if isinstance(converted, (bool, int, float, str)):
        return converted
    raise ULogEvidenceError(f"unsupported ULog scalar type: {type(converted).__name__}")


def extract_route_observations(data_list: Iterable[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    datasets = sorted(
        (item for item in data_list if item.name == "route_observability"),
        key=lambda item: int(item.multi_id),
    )
    if not datasets:
        raise ULogEvidenceError("route_observability is absent from the ULog")
    for dataset in datasets:
        missing = sorted(REQUIRED_FIELDS - set(dataset.data))
        if missing:
            raise ULogEvidenceError(
                f"route_observability[{dataset.multi_id}] lacks fields: "
                + ", ".join(missing)
            )
        row_count = len(dataset.data["timestamp"])
        for index in range(row_count):
            record = {
                field: _scalar(dataset.data[field][index])
                for field in sorted(REQUIRED_FIELDS)
            }
            record["ulog_multi_id"] = int(dataset.multi_id)
            record["ulog_row"] = index
            records.append(record)
    records.sort(
        key=lambda value: (
            int(value["timestamp"]),
            int(value["ulog_multi_id"]),
            int(value["sequence"]),
        )
    )
    return records


def sequence_gaps(records: Iterable[dict[str, Any]]) -> list[dict[str, int]]:
    by_instance: dict[int, list[int]] = {}
    for record in records:
        by_instance.setdefault(int(record["ulog_multi_id"]), []).append(
            int(record["sequence"])
        )
    gaps: list[dict[str, int]] = []
    for multi_id, values in sorted(by_instance.items()):
        # A publisher can exist before logger subscription starts. Its first
        # retained sequence is the evidence-window baseline, not proof of an
        # in-window dropout. Interior discontinuities remain fail-closed.
        for previous, current in zip(values, values[1:]):
            if current != previous + 1:
                gaps.append(
                    {
                        "ulog_multi_id": multi_id,
                        "previous_sequence": previous,
                        "current_sequence": current,
                    }
                )
    return gaps


def inspect_ulog(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        from pyulog import ULog
    except ImportError as exc:
        raise ULogEvidenceError("pyulog is required inside the formal container") from exc
    if not path.is_file():
        raise ULogEvidenceError(f"ULog does not exist: {path}")
    ulog = ULog(str(path), message_name_filter_list=["route_observability"])
    observations = extract_route_observations(ulog.data_list)
    gaps = sequence_gaps(observations)
    dropouts = [
        {"timestamp_us": int(item.timestamp), "duration_ms": int(item.duration)}
        for item in ulog.dropouts
    ]
    corruption = bool(ulog.file_corruption)
    status = "PASS" if not gaps and not dropouts and not corruption else "REJECT"
    summary = {
        "schema_version": "1.0",
        "status": status,
        "ulog_start_us": int(ulog.start_timestamp),
        "ulog_end_us": int(ulog.last_timestamp),
        "route_observation_count": len(observations),
        "route_observation_instances": sorted(
            {int(item["ulog_multi_id"]) for item in observations}
        ),
        "first_sequence_by_instance": {
            str(multi_id): min(
                int(item["sequence"])
                for item in observations
                if int(item["ulog_multi_id"]) == multi_id
            )
            for multi_id in sorted(
                {int(item["ulog_multi_id"]) for item in observations}
            )
        },
        "sequence_gaps": gaps,
        "dropouts": dropouts,
        "file_corruption": corruption,
    }
    return summary, observations


def _write_new(path: Path, value: Any) -> None:
    if path.exists():
        raise ULogEvidenceError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ulog", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary, observations = inspect_ulog(args.ulog)
        _write_new(args.summary, summary)
        _write_new(args.observations, observations)
    except (OSError, ULogEvidenceError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": summary["status"], "count": len(observations)}))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
