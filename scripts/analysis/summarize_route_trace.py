#!/usr/bin/env python3
"""Create a compact P0 summary from a canonical route trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tracing.actuator_writer_collector import summarize as summarize_writers
from scripts.oracles.route_oracle_v0 import run as run_oracle
from scripts.tracing.route_trace_collector import PROCESSED_ALLOCATOR_INPUT_STRIDE


def _artifact_identity(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def summarize(
    trace: Path,
    result: Path,
    scenario_label: str | None = None,
    sources: list[Path] | None = None,
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    nav_states: list[int] = []
    registration_states: list[object] = []
    first_timestamp: float | None = None
    last_timestamp: float | None = None
    max_message_age: float | None = None
    event_count = 0
    domain_ranges: dict[str, list[float]] = defaultdict(list)
    lifecycle_evidence: list[str] = []

    with trace.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            event_count += 1
            counts[str(event["event_type"])] += 1
            if str(event["event_type"]).startswith(("external_mode_", "executor_", "mode_executor_")):
                evidence = str(event["evidence_source"])
                if evidence not in lifecycle_evidence:
                    lifecycle_evidence.append(evidence)
            timestamp = float(event["timestamp"])
            domain = str(event["timestamp_domain"])
            domain_ranges[domain].append(timestamp)
            if domain == "ulog_us":
                first_timestamp = timestamp if first_timestamp is None else min(first_timestamp, timestamp)
                last_timestamp = timestamp if last_timestamp is None else max(last_timestamp, timestamp)
            mode = event.get("declared_mode")
            if domain == "ulog_us" and isinstance(mode, int) and (not nav_states or nav_states[-1] != mode):
                nav_states.append(mode)
            registration = event.get("registration_state")
            if registration is not None and (not registration_states or registration_states[-1] != registration):
                registration_states.append(registration)
            age = event.get("message_age")
            if isinstance(age, (int, float)):
                max_message_age = float(age) if max_message_age is None else max(max_message_age, float(age))

    baseline = json.loads(result.read_text(encoding="utf-8"))
    if scenario_label is not None:
        baseline["runner_scenario"] = baseline.get("scenario")
        baseline["scenario"] = scenario_label
    oracle = run_oracle(trace)
    return {
        "schema_version": "1.1",
        "run_id": trace.parent.name,
        "execution_status": baseline.get("status", "UNKNOWN"),
        "route_verdict": oracle["status"],
        "baseline": baseline,
        "trace_event_count": event_count,
        "event_type_counts": dict(sorted(counts.items())),
        "first_timestamp_us": first_timestamp,
        "last_timestamp_us": last_timestamp,
        "duration_us": None if first_timestamp is None or last_timestamp is None else last_timestamp - first_timestamp,
        "timestamp_domains": {
            domain: {
                "event_count": len(values),
                "first": min(values),
                "last": max(values),
                "duration": max(values) - min(values),
            }
            for domain, values in sorted(domain_ranges.items())
        },
        "nav_state_transitions": nav_states,
        "registration_transitions": registration_states,
        "max_message_age_s": max_message_age,
        "writer_attribution": summarize_writers(trace),
        "producer_consumer_evidence": {
            "producer_publish_events": counts["producer_still_publishing"],
            "px4_consume_events": counts["px4_setpoint_consumed"],
            "domains_require_clock_bridge": len(domain_ranges) > 1,
        },
        "lifecycle_evidence": lifecycle_evidence,
        "source_artifacts": [_artifact_identity(path) for path in (sources or [])],
        "processed_trace_policy": {
            "actuator_output_stride": 1,
            "allocator_input_stride": PROCESSED_ALLOCATOR_INPUT_STRIDE,
            "complete_source": "source_artifacts ULog",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario-label")
    parser.add_argument("--source", action="append", type=Path, default=[])
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            summarize(args.trace, args.result, args.scenario_label, args.source),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
