#!/usr/bin/env python3
"""Evaluate the ten P-1 entry criteria from concrete repository/build evidence."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Callable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "config" / "dependencies.lock.yaml"
MATRIX = ROOT / "docs" / "design" / "OBSERVABILITY_MATRIX.tsv"
RESULT = ROOT / "experiments" / "motivation" / "p1_gate_result.json"


def locked(path: str) -> str:
    return subprocess.check_output(
        ["python3", str(ROOT / "scripts" / "setup" / "verify_dependency_lock.py"), "--get", path],
        cwd=ROOT,
        text=True,
    ).strip()


def official_binary(name: str) -> bool:
    install = ROOT / "ros2_ws" / "install"
    return install.is_dir() and any(path.is_file() and path.stat().st_mode & 0o111 for path in install.rglob(name))


def matrix_rows() -> list[dict[str, str]]:
    with MATRIX.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def main() -> int:
    rows = matrix_rows()
    expected = {
        "declared_mode",
        "registration_state",
        "authority_source",
        "producer_identity",
        "setpoint_level",
        "setpoint_topic",
        "message_freshness",
        "enabled_modules",
        "bypassed_modules",
        "allocator_input",
        "actuator_writer",
        "actuator_output",
        "failsafe_state",
        "fallback_target",
    }
    patch = ROOT / "patches" / "px4" / "route_observability" / "route_observability_topics.patch"
    px4 = ROOT / "external" / "PX4-Autopilot"
    patched_binary = (
        ROOT
        / "external"
        / "PX4-Autopilot-route-observability"
        / "build"
        / "px4_sitl_default"
        / "bin"
        / "px4"
    )
    timestamp_model = (ROOT / "docs" / "design" / "TIMESTAMP_MODEL.md").read_text(encoding="utf-8")
    timestamp_model_lower = timestamp_model.lower()
    collector = (ROOT / "scripts" / "tracing" / "route_trace_collector.py").read_text(encoding="utf-8")
    bootstrap_log = ROOT / "runs" / "setup" / "family_a_bootstrap.log"
    schema = json.loads((ROOT / "data" / "schemas" / "route_trace.schema.json").read_text(encoding="utf-8"))

    def patch_applicable() -> bool:
        return (
            subprocess.run(
                ["git", "apply", "--check", str(patch)], cwd=px4, capture_output=True, text=True
            ).returncode
            == 0
        )

    checks: list[tuple[str, str, Callable[[], bool], str]] = [
        (
            "route_fields_classified",
            "All 14 route fields have one allowed observability status.",
            lambda: {row["route_field"] for row in rows} == expected
            and all(row["status"] in {"DIRECT", "DERIVED", "INSTRUMENTATION_REQUIRED", "UNOBSERVABLE"} for row in rows),
            str(MATRIX.relative_to(ROOT)),
        ),
        (
            "direct_derived_collectors",
            "Every DIRECT/DERIVED field identifies source and collection implementation.",
            lambda: all(
                row["source_path"].strip() and row["symbol"].strip() and row["collection_method"].strip()
                for row in rows
                if row["status"] in {"DIRECT", "DERIVED"}
            )
            and (ROOT / "scripts" / "tracing" / "route_trace_collector.py").is_file(),
            "OBSERVABILITY_MATRIX.tsv + scripts/tracing/route_trace_collector.py",
        ),
        (
            "instrumentation_applies_and_builds",
            "Required observation-only patch applies and its PX4 SITL binary is built.",
            lambda: patch_applicable() and patched_binary.is_file() and patched_binary.stat().st_mode & 0o111,
            "patches/px4/route_observability/route_observability_topics.patch + patched bin/px4",
        ),
        (
            "timestamp_event_ordering",
            "Timestamp model defines offsets/clock bridge and sortable ULog/PX4 domains.",
            lambda: all(
                token in timestamp_model_lower
                for token in ("offset", "clock bridge", "overlap", "gap", "replay")
            ),
            "docs/design/TIMESTAMP_MODEL.md",
        ),
        (
            "producer_vs_consumer",
            "Collector separates producer publication from PX4 setpoint consumption.",
            lambda: "producer_still_publishing" in collector and "px4_setpoint_consumed" in collector,
            "scripts/tracing/route_trace_collector.py + tests/test_route_trace_schema.py",
        ),
        (
            "final_actuator_writer",
            "Final actuator writer has explicit, built instrumentation and a collector mapping.",
            lambda: "actuator_output_published" in collector
            and "WRITER_CONTROL_ALLOCATOR" in patch.read_text(encoding="utf-8")
            and patched_binary.is_file(),
            "route_observability patch + actuator_writer_collector.py",
        ),
        (
            "family_a_build",
            "Unified Family A bootstrap completed.",
            lambda: bootstrap_log.is_file() and "FAMILY_A_BOOTSTRAP=PASS" in bootstrap_log.read_text(encoding="utf-8"),
            "runs/setup/family_a_bootstrap.log",
        ),
        (
            "external_mode_basic_build",
            "Official External Mode basic example compiled.",
            lambda: official_binary("example_mode_goto"),
            "ros2_ws/install/**/example_mode_goto",
        ),
        (
            "mode_executor_build",
            "Official Mode Executor example compiled.",
            lambda: official_binary("example_mode_with_executor"),
            "ros2_ws/install/**/example_mode_with_executor",
        ),
        (
            "trace_schema_collector",
            "Route trace schema and collector contract are loadable and valid.",
            lambda: not Draft202012Validator.check_schema(schema)
            and (ROOT / "tests" / "test_route_trace_schema.py").is_file(),
            "route_trace.schema.json + tests/test_route_trace_schema.py",
        ),
    ]

    criteria: list[dict[str, object]] = []
    blocking: list[str] = []
    for identifier, description, check, evidence in checks:
        try:
            passed = bool(check())
            detail = ""
        except Exception as exc:  # gate must fail closed
            passed = False
            detail = f" ({type(exc).__name__}: {exc})"
        criteria.append(
            {
                "id": identifier,
                "status": "PASS" if passed else "FAIL",
                "description": description,
                "evidence": evidence,
            }
        )
        if not passed:
            blocking.append(identifier + detail)

    result = {
        "status": "PASS" if not blocking else "FAIL",
        "criteria": criteria,
        "blocking_items": blocking,
        "px4_commit": locked("px4_autopilot.commit"),
        "px4_msgs_commit": locked("px4_msgs.commit"),
        "px4_ros2_interface_lib_commit": locked("px4_ros2_interface_lib.commit"),
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
