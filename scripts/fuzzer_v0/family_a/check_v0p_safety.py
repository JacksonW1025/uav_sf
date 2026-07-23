#!/usr/bin/env python3
"""Apply the frozen Family A V0-P safety boundaries to static evidence."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.fuzzer_v0.family_a.common import FAMILY_BASE, read_yaml


STATUSES = {
    "PASS",
    "FORMAL_SAFETY_STOP",
    "MEASUREMENT_INSUFFICIENT",
    "ENVIRONMENT_FAILURE",
    "CAMPAIGN_CONFIGURATION_FAILURE",
}
FINITE_FIELDS = (
    "command_values",
    "observed_controller_values",
    "actuator_observations",
)
NUMERIC_FIELDS = (
    "target_takeoff_altitude_m",
    "baseline_altitude_m",
    "minimum_altitude_m",
    "maximum_commanded_horizontal_speed_m_s",
    "maximum_observed_horizontal_speed_m_s",
    "maximum_commanded_vertical_speed_abs_m_s",
    "maximum_observed_vertical_speed_abs_m_s",
    "maximum_attitude_excursion_deg",
    "maximum_body_rate_rad_s",
)
BOOLEAN_FIELDS = (
    "unexpected_ground_contact",
    "px4_abort",
    "clock_stall",
    "critical_window_complete",
    "route_epoch_present",
    "writer_lineage_present",
    "controller_lineage_present",
    "land_completed",
    "disarm_completed",
    "runner_timed_out",
    "environment_failure",
    "campaign_configuration_failure",
)


def _finite_sequence(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value
        )
    )


def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    rules = read_yaml(FAMILY_BASE / "safety_rules.yaml")
    bounds = rules["physical_boundaries"]
    reasons: list[str] = []
    missing = [
        name
        for name in (*FINITE_FIELDS, *NUMERIC_FIELDS, *BOOLEAN_FIELDS)
        if name not in record or record[name] is None
    ]
    if missing:
        return {
            "schema_version": "1.0",
            "status": "MEASUREMENT_INSUFFICIENT",
            "reasons": ["missing_required_safety_evidence"],
            "missing_fields": missing,
            "bounds_source": "experiments/fuzzer_v0/family_a/safety_rules.yaml",
            "W1_or_B1_envelope_used": False,
        }

    if bool(record["campaign_configuration_failure"]):
        status = "CAMPAIGN_CONFIGURATION_FAILURE"
        reasons.append("campaign_configuration_failure")
    elif bool(record["environment_failure"]):
        status = "ENVIRONMENT_FAILURE"
        reasons.append("environment_failure")
    else:
        status = "PASS"
        for field in FINITE_FIELDS:
            if not _finite_sequence(record[field]):
                reasons.append(f"non_finite_or_empty_{field}")
        for field in NUMERIC_FIELDS:
            value = record[field]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                reasons.append(f"non_finite_{field}")

        if reasons:
            status = "FORMAL_SAFETY_STOP"
        else:
            altitude_loss = float(record["baseline_altitude_m"]) - float(
                record["minimum_altitude_m"]
            )
            checks = (
                (
                    float(record["target_takeoff_altitude_m"])
                    < float(bounds["target_takeoff_altitude_minimum_m"]),
                    "target_takeoff_altitude_below_frozen_minimum",
                ),
                (
                    altitude_loss
                    > float(bounds["maximum_altitude_loss_from_stable_baseline_m"]),
                    "height_boundary_exceeded",
                ),
                (
                    float(record["maximum_commanded_horizontal_speed_m_s"])
                    > float(bounds["maximum_commanded_horizontal_speed_m_s"]),
                    "commanded_horizontal_speed_boundary_exceeded",
                ),
                (
                    float(record["maximum_observed_horizontal_speed_m_s"])
                    > float(bounds["maximum_observed_horizontal_speed_m_s"]),
                    "observed_horizontal_speed_boundary_exceeded",
                ),
                (
                    float(record["maximum_commanded_vertical_speed_abs_m_s"])
                    > float(bounds["maximum_commanded_vertical_speed_abs_m_s"]),
                    "commanded_vertical_speed_boundary_exceeded",
                ),
                (
                    float(record["maximum_observed_vertical_speed_abs_m_s"])
                    > float(bounds["maximum_observed_vertical_speed_abs_m_s"]),
                    "observed_vertical_speed_boundary_exceeded",
                ),
                (
                    float(record["maximum_attitude_excursion_deg"])
                    > float(bounds["maximum_attitude_excursion_deg"]),
                    "attitude_boundary_exceeded",
                ),
                (
                    float(record["maximum_body_rate_rad_s"])
                    > float(bounds["maximum_body_rate_rad_s"]),
                    "body_rate_boundary_exceeded",
                ),
                (
                    bool(record["unexpected_ground_contact"]),
                    "unexpected_ground_contact",
                ),
                (bool(record["px4_abort"]), "PX4_abort"),
                (bool(record["clock_stall"]), "clock_stall"),
                (bool(record["runner_timed_out"]), "runner_timeout"),
            )
            reasons.extend(reason for failed, reason in checks if failed)
            evidence_checks = (
                ("critical_window_complete", "incomplete_critical_window"),
                ("route_epoch_present", "missing_route_epoch"),
                ("writer_lineage_present", "missing_writer_lineage"),
                ("controller_lineage_present", "missing_controller_lineage"),
                ("land_completed", "missing_Land_completion"),
                ("disarm_completed", "missing_Disarm_completion"),
            )
            missing_evidence = [
                reason for field, reason in evidence_checks if not bool(record[field])
            ]
            if reasons:
                status = "FORMAL_SAFETY_STOP"
            elif missing_evidence:
                status = "MEASUREMENT_INSUFFICIENT"
                reasons.extend(missing_evidence)

    assert status in STATUSES
    return {
        "schema_version": "1.0",
        "status": status,
        "reasons": reasons,
        "missing_fields": [],
        "bounds": {
            key: value
            for key, value in bounds.items()
            if key not in {"provenance", "W1_or_B1_envelope_used"}
        },
        "bounds_source": "experiments/fuzzer_v0/family_a/safety_rules.yaml",
        "W1_or_B1_envelope_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("safety input must be a JSON object")
    result = evaluate(value)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
